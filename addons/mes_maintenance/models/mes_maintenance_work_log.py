from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .mes_maintenance_equipment import GROUP_TECHNICIAN, _technician_domain


class MesMaintenanceLineMixin(models.AbstractModel):
    """작업 기록·비용 공통: 요청 상태와 작업 권한을 검사한다."""
    _name = 'mes.maintenance.line.mixin'
    _description = '정비 요청 하위 항목 공통'

    def _check_request_workable(self, requests):
        if self.env.su:
            return
        requests = requests.exists()
        for request in requests:
            if request.state != 'accepted' and request.state != 'in_progress':
                raise ValidationError(
                    f'{request.name}: 작업 기록과 비용은 접수·작업 중 상태에서만 추가·수정·삭제할 수 있습니다.')
        requests._check_can_work()

    @api.model_create_multi
    def create(self, vals_list):
        request_ids = {vals.get('request_id') for vals in vals_list if vals.get('request_id')}
        self._check_request_workable(self.env['mes.maintenance.request'].browse(list(request_ids)))
        return super().create(vals_list)

    def write(self, vals):
        requests = self.request_id
        if vals.get('request_id'):
            requests |= self.env['mes.maintenance.request'].browse(vals['request_id'])
        self._check_request_workable(requests)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_check_request(self):
        self._check_request_workable(self.request_id)


class MesMaintenanceWorkLog(models.Model):
    _name = 'mes.maintenance.work.log'
    _inherit = ['mes.maintenance.line.mixin']
    _description = '작업 기록'
    _order = 'date desc, id desc'

    request_id = fields.Many2one('mes.maintenance.request', string='정비 요청', required=True,
                                 ondelete='cascade', index=True)
    date = fields.Datetime('작업 일시', required=True, default=fields.Datetime.now)
    user_id = fields.Many2one('res.users', string='작업자', required=True, ondelete='restrict',
                              default=lambda self: self.env.user,
                              domain=lambda self: _technician_domain(self))
    hours = fields.Float('소요 시간(시간)', default=0.0)
    description = fields.Text('작업 내용')

    _hours_positive = models.Constraint('CHECK(hours >= 0)', '소요 시간은 음수일 수 없습니다.')

    @api.constrains('hours')
    def _check_hours(self):
        for log in self:
            if log.hours < 0:
                raise ValidationError('소요 시간은 음수일 수 없습니다.')

    @api.constrains('user_id')
    def _check_user(self):
        group = self.env.ref(GROUP_TECHNICIAN)
        for log in self:
            if log.user_id and group not in log.user_id.sudo().all_group_ids:
                raise ValidationError('작업자는 정비원 그룹의 사용자여야 합니다.')
