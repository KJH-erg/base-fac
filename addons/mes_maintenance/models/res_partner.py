from odoo import fields, models

GROUP_TECHNICIAN = 'mes_maintenance.group_mes_maintenance_technician'


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mes_maintenance_cost_total = fields.Monetary(
        '정비 비용 합계', compute='_compute_mes_maintenance_cost_total',
        currency_field='mes_maintenance_currency_id', groups=GROUP_TECHNICIAN,
        help='완료된 정비 요청에서 이 업체에 지급한 비용의 합계')
    mes_maintenance_currency_id = fields.Many2one(
        'res.currency', string='정비 통화', compute='_compute_mes_maintenance_cost_total',
        groups=GROUP_TECHNICIAN)

    def _done_cost_domain(self):
        return [('partner_id', 'in', self.ids), ('request_id.state', '=', 'done')]

    def _compute_mes_maintenance_cost_total(self):
        Cost = self.env['mes.maintenance.cost'].sudo()
        totals = dict(Cost._read_group(self._done_cost_domain(), ['partner_id'], ['amount:sum']))
        currency = self.env.company.currency_id
        for partner in self:
            partner.mes_maintenance_currency_id = currency
            partner.mes_maintenance_cost_total = totals.get(partner, 0.0) if partner.id else 0.0

    def action_view_mes_maintenance_costs(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('mes_maintenance.action_mes_maintenance_cost')
        action['domain'] = [('partner_id', '=', self.id), ('request_id.state', '=', 'done')]
        action['context'] = {'create': False}
        return action
