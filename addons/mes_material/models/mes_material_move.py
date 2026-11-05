from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero

QTY_DIGITS = 3


class MesMaterialMove(models.Model):
    _name = 'mes.material.move'
    _description = '입출고'
    _order = 'date desc, id desc'

    name = fields.Char(string='번호', required=True, readonly=True, copy=False, default=lambda self: _('새 항목'))
    move_type = fields.Selection(
        [('in', '입고'), ('out', '출고'), ('adjust', '조정')],
        string='유형', required=True, default='in')
    material_id = fields.Many2one(
        'mes.material', string='자재', required=True, ondelete='restrict', index=True,
        domain="[('active', '=', True)]")
    uom = fields.Char(related='material_id.uom', string='단위')
    qty = fields.Float(string='수량', digits=(16, QTY_DIGITS), default=0.0,
                       help='조정은 음수(예: -3)를 넣을 수 있습니다.')
    date = fields.Date(string='일자', required=True, default=fields.Date.context_today)
    user_id = fields.Many2one('res.users', string='담당자', required=True,
                              default=lambda self: self.env.user)
    partner_id = fields.Many2one('res.partner', string='공급처')
    reason = fields.Text(string='사유')
    state = fields.Selection(
        [('draft', '초안'), ('done', '확정'), ('cancel', '취소')],
        string='상태', required=True, default='draft', readonly=True, copy=False, index=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _signed_qty(self):
        """Effect of this move on the on-hand quantity (when confirmed)."""
        self.ensure_one()
        if self.move_type == 'out':
            return -self.qty
        return self.qty

    def _set_state(self, state):
        # Bypass the write() guard below: the state only changes through the actions.
        return super(MesMaterialMove, self).write({'state': state})

    def _check_on_hand_after(self, material, delta, message):
        material.sudo().lock_for_update()
        material.invalidate_recordset(['qty_on_hand', 'is_shortage'])
        new_qty = material.qty_on_hand + delta
        if float_compare(new_qty, 0.0, precision_digits=QTY_DIGITS) < 0:
            raise UserError(_(
                '%(message)s (%(name)s, 자재 %(material)s, 현재고 %(on_hand)s %(uom)s)',
                message=message, name=self.name, material=material.display_name,
                on_hand=material.qty_on_hand, uom=material.uom or ''))

    # ------------------------------------------------------------------
    # Constraints / onchanges
    # ------------------------------------------------------------------
    @api.constrains('move_type', 'reason')
    def _check_reason(self):
        for move in self:
            if move.move_type == 'adjust' and not (move.reason or '').strip():
                raise ValidationError(_('조정에는 사유를 반드시 적어야 합니다.'))

    @api.onchange('move_type')
    def _onchange_move_type(self):
        if self.move_type != 'in':
            self.partner_id = False

    @api.onchange('material_id')
    def _onchange_material_id(self):
        if self.move_type == 'in' and self.material_id.partner_id and not self.partner_id:
            self.partner_id = self.material_id.partner_id

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model
    def _check_material_active(self, material_ids):
        materials = self.env['mes.material'].with_context(active_test=False).browse(material_ids).exists()
        inactive = materials.filtered(lambda m: not m.active)
        if inactive:
            raise UserError(_('사용 중지된 자재는 입출고에 고를 수 없습니다: %s',
                              ', '.join(inactive.mapped('display_name'))))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'draft') != 'draft':
                raise UserError(_('상태는 확정·취소 동작으로만 바꿀 수 있습니다.'))
            vals.pop('state', None)
        self._check_material_active([vals['material_id'] for vals in vals_list if vals.get('material_id')])
        for vals in vals_list:
            seq_date = vals.get('date') or fields.Date.context_today(self)
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code(
                'mes.material.move', sequence_date=seq_date) or _('새 항목')
        return super().create(vals_list)

    def write(self, vals):
        if 'state' in vals:
            raise UserError(_('상태는 확정·취소 동작으로만 바꿀 수 있습니다.'))
        if self.filtered(lambda m: m.state != 'draft'):
            raise UserError(_('확정되거나 취소된 입출고는 고칠 수 없습니다.'))
        if 'name' in vals and any(m.name != vals['name'] for m in self):
            raise UserError(_('번호는 고칠 수 없습니다.'))
        if vals.get('material_id'):
            self._check_material_active([vals['material_id']])
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if self.filtered(lambda m: m.state != 'draft'):
            raise UserError(_('초안 입출고만 지울 수 있습니다.'))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.check_access('write')
        for move in self:
            if move.state != 'draft':
                raise UserError(_('초안 상태의 입출고만 확정할 수 있습니다. (%s)', move.name))
            if move.move_type in ('in', 'out'):
                if float_compare(move.qty, 0.0, precision_digits=QTY_DIGITS) <= 0:
                    raise UserError(_('입고·출고 수량은 0보다 커야 합니다. (%s)', move.name))
            elif float_is_zero(move.qty, precision_digits=QTY_DIGITS):
                raise UserError(_('조정 수량은 0이 아니어야 합니다. (%s)', move.name))
            if move.move_type == 'adjust' and not (move.reason or '').strip():
                raise UserError(_('조정에는 사유를 반드시 적어야 합니다. (%s)', move.name))
            move._check_on_hand_after(
                move.material_id, move._signed_qty(),
                _('현재고가 음수가 되므로 확정할 수 없습니다.'))
            move._set_state('done')
        return True

    def action_cancel(self):
        self.check_access('write')
        is_manager = self.env.user.has_group('mes_material.group_mes_material_manager')
        for move in self:
            if move.state == 'cancel':
                raise UserError(_('이미 취소된 입출고입니다. (%s)', move.name))
            if move.state == 'done':
                if not is_manager:
                    raise AccessError(_('확정된 입출고는 자재 관리자만 취소할 수 있습니다. (%s)', move.name))
                move._check_on_hand_after(
                    move.material_id, -move._signed_qty(),
                    _('취소하면 현재고가 음수가 되므로 취소할 수 없습니다.'))
            move._set_state('cancel')
        return True
