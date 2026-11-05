from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MesMaterial(models.Model):
    _name = 'mes.material'
    _description = '자재'
    _order = 'code'
    _rec_names_search = ['code', 'name']

    code = fields.Char(string='코드', required=True, copy=False)
    name = fields.Char(string='이름', required=True)
    uom = fields.Char(string='단위', required=True, default='EA', help='예: EA, kg')
    safety_qty = fields.Float(string='안전 재고', digits=(16, 3), default=0.0)
    qty_on_hand = fields.Float(
        string='현재고', digits=(16, 3), compute='_compute_qty_on_hand', store=True,
        help='확정된 입출고로 계산됩니다. 바꾸려면 조정 입출고를 확정하세요.')
    is_shortage = fields.Boolean(
        string='재고 부족', compute='_compute_is_shortage', store=True,
        help='현재고가 안전 재고보다 적습니다.')
    partner_id = fields.Many2one('res.partner', string='기본 공급처', ondelete='set null')
    active = fields.Boolean(string='사용', default=True)
    move_ids = fields.One2many('mes.material.move', 'material_id', string='입출고')
    move_count = fields.Integer(string='입출고 수', compute='_compute_move_count')
    alert_ids = fields.One2many('mes.material.alert', 'material_id', string='재고 부족 경고')

    _code_uniq = models.Constraint('UNIQUE(code)', '같은 자재 코드가 이미 있습니다.')

    @api.depends('move_ids.state', 'move_ids.qty', 'move_ids.move_type')
    def _compute_qty_on_hand(self):
        for material in self:
            material.qty_on_hand = sum(
                move._signed_qty() for move in material.move_ids if move.state == 'done'
            )

    @api.depends('qty_on_hand', 'safety_qty')
    def _compute_is_shortage(self):
        for material in self:
            material.is_shortage = material.qty_on_hand < material.safety_qty

    def _compute_move_count(self):
        counts = dict(self.env['mes.material.move']._read_group(
            [('material_id', 'in', self.ids)], ['material_id'], ['__count']))
        for material in self:
            material.move_count = counts.get(material, 0)

    @api.depends('code', 'name')
    def _compute_display_name(self):
        for material in self:
            material.display_name = f'[{material.code}] {material.name}' if material.code else material.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_protected_fields(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._check_protected_fields(vals)
        return super().write(vals)

    @api.model
    def _check_protected_fields(self, vals):
        if {'qty_on_hand', 'is_shortage'} & set(vals):
            raise UserError(_('현재고는 직접 고칠 수 없습니다. 조정 입출고를 확정해 바꾸세요.'))

    def copy_data(self, default=None):
        vals_list = super().copy_data(default=default)
        if not (default and 'code' in default):
            for material, vals in zip(self, vals_list):
                vals['code'] = _('%s (복사)', material.code)
        return vals_list

    @api.ondelete(at_uninstall=False)
    def _unlink_except_has_moves(self):
        moves = self.env['mes.material.move'].sudo().search_count(
            [('material_id', 'in', self.ids)], limit=1)
        if moves:
            raise UserError(_('입출고가 있는 자재는 지울 수 없습니다. 대신 사용 중지하세요.'))
        alerts = self.env['mes.material.alert'].sudo().search_count(
            [('material_id', 'in', self.ids)], limit=1)
        if alerts:
            raise UserError(_('재고 부족 경고가 있는 자재는 지울 수 없습니다. 대신 사용 중지하세요.'))

    def action_view_moves(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('mes_material.action_mes_material_move')
        action['domain'] = [('material_id', '=', self.id)]
        action['context'] = {'default_material_id': self.id}
        action['display_name'] = _('입출고 내역: %s', self.display_name)
        return action
