from odoo import fields, models


class MesMaintenanceRejectWizard(models.TransientModel):
    _name = 'mes.maintenance.reject.wizard'
    _description = '정비 요청 반려'

    request_id = fields.Many2one('mes.maintenance.request', string='정비 요청', required=True,
                                 ondelete='cascade')
    reason = fields.Text('반려 사유', required=True)

    def action_confirm(self):
        self.ensure_one()
        self.request_id._do_reject(self.reason)
        return {'type': 'ir.actions.act_window_close'}
