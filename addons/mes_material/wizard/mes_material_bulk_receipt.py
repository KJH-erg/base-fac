from odoo import Command, api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare, float_is_zero


class MesMaterialBulkReceipt(models.TransientModel):
    _name = 'mes.material.bulk.receipt'
    _description = '일괄 입고'

    partner_id = fields.Many2one('res.partner', string='공급처', required=True)
    date = fields.Date(string='일자', required=True, default=fields.Date.context_today)
    line_ids = fields.One2many('mes.material.bulk.receipt.line', 'wizard_id', string='자재별 수량')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'line_ids' in fields_list and not res.get('line_ids'):
            materials = self.env['mes.material'].search([('active', '=', True)])
            res['line_ids'] = [Command.create({'material_id': m.id, 'qty': 0.0}) for m in materials]
        return res

    def action_confirm(self):
        self.ensure_one()
        lines = self.line_ids.filtered(lambda l: not float_is_zero(l.qty, precision_digits=3))
        if not lines:
            raise UserError(_('수량을 넣은 자재가 없습니다. 입고할 자재의 수량을 입력하세요.'))
        negative = lines.filtered(lambda l: float_compare(l.qty, 0.0, precision_digits=3) < 0)
        if negative:
            raise UserError(_('입고 수량은 0보다 커야 합니다: %s',
                              ', '.join(negative.material_id.mapped('display_name'))))
        moves = self.env['mes.material.move'].create([{
            'move_type': 'in',
            'material_id': line.material_id.id,
            'qty': line.qty,
            'date': self.date,
            'partner_id': self.partner_id.id,
        } for line in lines])
        moves.action_confirm()
        action = self.env['ir.actions.act_window']._for_xml_id('mes_material.action_mes_material_move')
        action['domain'] = [('id', 'in', moves.ids)]
        action['context'] = {}
        action['display_name'] = _('일괄 입고 결과')
        return action


class MesMaterialBulkReceiptLine(models.TransientModel):
    _name = 'mes.material.bulk.receipt.line'
    _description = '일괄 입고 줄'

    wizard_id = fields.Many2one('mes.material.bulk.receipt', required=True, ondelete='cascade')
    material_id = fields.Many2one('mes.material', string='자재', required=True,
                                  domain="[('active', '=', True)]")
    uom = fields.Char(related='material_id.uom', string='단위')
    qty_on_hand = fields.Float(related='material_id.qty_on_hand', string='현재고')
    qty = fields.Float(string='입고 수량', digits=(16, 3), default=0.0)
