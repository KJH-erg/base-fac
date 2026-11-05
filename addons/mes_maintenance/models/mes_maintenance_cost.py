from odoo import api, fields, models
from odoo.exceptions import ValidationError


class MesMaintenanceCost(models.Model):
    _name = 'mes.maintenance.cost'
    _inherit = ['mes.maintenance.line.mixin']
    _description = '정비 비용'
    _order = 'id'

    request_id = fields.Many2one('mes.maintenance.request', string='정비 요청', required=True,
                                 ondelete='cascade', index=True)
    request_state = fields.Selection(related='request_id.state', string='요청 상태')
    equipment_id = fields.Many2one(related='request_id.equipment_id', string='설비')
    cost_type = fields.Selection([
        ('parts', '부품'),
        ('outsource', '외주'),
        ('other', '기타'),
    ], string='항목', required=True, default='parts')
    description = fields.Char('설명')
    amount = fields.Monetary('금액', currency_field='currency_id', default=0.0)
    currency_id = fields.Many2one('res.currency', string='통화', required=True,
                                  default=lambda self: self.env.company.currency_id)
    partner_id = fields.Many2one('res.partner', string='외부 업체', index=True, ondelete='restrict')

    _amount_positive = models.Constraint('CHECK(amount >= 0)', '금액은 음수일 수 없습니다.')

    @api.constrains('amount')
    def _check_amount(self):
        for cost in self:
            if cost.amount < 0:
                raise ValidationError('금액은 음수일 수 없습니다.')
