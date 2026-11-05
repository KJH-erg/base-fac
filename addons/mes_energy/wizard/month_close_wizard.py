from odoo import fields, models

MONTH_SELECTION = [(str(m), '%d월' % m) for m in range(1, 13)]


class MesEnergyMonthCloseWizard(models.TransientModel):
    _name = 'mes.energy.month.close.wizard'
    _description = '에너지 월 마감하기'

    year = fields.Integer(string='연도', required=True,
                          default=lambda self: fields.Date.context_today(self).year)
    month = fields.Selection(MONTH_SELECTION, string='월', required=True,
                             default=lambda self: str(fields.Date.context_today(self).month))

    def action_close(self):
        self.ensure_one()
        name = '%04d-%02d' % (self.year, int(self.month))
        self.env['mes.energy.month.close'].create({'name': name})
        return self.env['ir.actions.act_window']._for_xml_id('mes_energy.action_mes_energy_month_close')
