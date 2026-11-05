from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MesMaterialAlert(models.Model):
    _name = 'mes.material.alert'
    _description = '재고 부족 경고'
    _order = 'check_datetime desc, id desc'
    _rec_name = 'material_id'

    material_id = fields.Many2one('mes.material', string='자재', required=True, readonly=True,
                                  ondelete='restrict', index=True)
    uom = fields.Char(related='material_id.uom', string='단위')
    check_datetime = fields.Datetime(string='확인 일시', required=True, readonly=True,
                                     default=fields.Datetime.now)
    qty_on_hand = fields.Float(string='당시 현재고', digits=(16, 3), readonly=True)
    safety_qty = fields.Float(string='당시 안전 재고', digits=(16, 3), readonly=True)
    is_done = fields.Boolean(string='처리 완료', default=False, readonly=True, index=True)
    done_user_id = fields.Many2one('res.users', string='처리자', readonly=True)
    done_datetime = fields.Datetime(string='처리 일시', readonly=True)

    _WRITABLE_FIELDS = {'is_done', 'done_user_id', 'done_datetime'}

    def write(self, vals):
        if not self.env.su and set(vals) - self._WRITABLE_FIELDS:
            raise UserError(_('재고 부족 경고의 내용은 고칠 수 없습니다. 처리 완료 표시만 할 수 있습니다.'))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self):
        raise UserError(_('재고 부족 경고는 지울 수 없습니다.'))

    def action_mark_done(self):
        todo = self.filtered(lambda a: not a.is_done)
        todo.write({
            'is_done': True,
            'done_user_id': self.env.user.id,
            'done_datetime': fields.Datetime.now(),
        })
        return True

    @api.model
    def _cron_check_shortage(self):
        """Daily: create an alert for every active material in shortage,
        unless an unprocessed alert already exists for it."""
        materials = self.env['mes.material'].search([('active', '=', True), ('is_shortage', '=', True)])
        if not materials:
            return
        pending = self.search([('material_id', 'in', materials.ids), ('is_done', '=', False)])
        to_alert = materials - pending.material_id
        now = fields.Datetime.now()
        self.create([{
            'material_id': material.id,
            'check_datetime': now,
            'qty_on_hand': material.qty_on_hand,
            'safety_qty': material.safety_qty,
        } for material in to_alert])
