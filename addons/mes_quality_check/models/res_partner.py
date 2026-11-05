from odoo import _, fields, models

from .mes_qc_common import GROUP_INSPECTOR


class ResPartner(models.Model):
    _inherit = 'res.partner'

    mes_qc_inspection_count = fields.Integer(
        string='검사 수', compute='_compute_mes_qc_counts', groups=GROUP_INSPECTOR,
        help='이 거래처의 완료된 검사 수')
    mes_qc_failed_count = fields.Integer(
        string='불합격 수', compute='_compute_mes_qc_counts', groups=GROUP_INSPECTOR,
        help='이 거래처의 완료된 검사 중 불합격 수')

    def _compute_mes_qc_counts(self):
        data = self.env['mes.qc.inspection']._read_group(
            [('partner_id', 'in', self.ids), ('state', '=', 'done')],
            ['partner_id', 'result'], ['__count'])
        totals = {}
        failed = {}
        for partner, result, count in data:
            totals[partner.id] = totals.get(partner.id, 0) + count
            if result == 'fail':
                failed[partner.id] = failed.get(partner.id, 0) + count
        for partner in self:
            partner.mes_qc_inspection_count = totals.get(partner.id, 0)
            partner.mes_qc_failed_count = failed.get(partner.id, 0)

    def _mes_qc_inspection_action(self, extra_domain, name):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'mes.qc.inspection',
            'view_mode': 'list,form',
            'views': [(False, 'list'), (False, 'form')],
            'domain': [('partner_id', '=', self.id), ('state', '=', 'done')] + extra_domain,
            'context': {'default_partner_id': self.id},
        }

    def action_open_mes_qc_inspections(self):
        return self._mes_qc_inspection_action([], _('%s의 완료된 검사', self.display_name))

    def action_open_mes_qc_failed_inspections(self):
        return self._mes_qc_inspection_action(
            [('result', '=', 'fail')], _('%s의 불합격 검사', self.display_name))
