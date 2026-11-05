from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .mes_maintenance_equipment import GROUP_TECHNICIAN, _technician_domain

GROUP_MANAGER = 'mes_maintenance.group_mes_maintenance_manager'

# 요청 상태에서 요청자 본인 또는 관리자가 고칠 수 있는 항목
REQUEST_EDIT_FIELDS = {'equipment_id', 'maintenance_type', 'priority', 'symptom'}
# 접수·작업 중 상태에서 배정 정비원 또는 관리자가 고칠 수 있는 항목
WORK_FIELDS = {'work_log_ids', 'cost_ids'}
OPEN_STATES = ('request', 'accepted', 'in_progress')
WORK_STATES = ('accepted', 'in_progress')
CLOSED_STATES = ('done', 'rejected')


class MesMaintenanceRequest(models.Model):
    _name = 'mes.maintenance.request'
    _description = '정비 요청'
    _order = 'id desc'

    name = fields.Char('번호', readonly=True, copy=False, default='새 요청')
    equipment_id = fields.Many2one('mes.maintenance.equipment', string='설비', required=True,
                                   ondelete='restrict', index=True)
    requester_id = fields.Many2one('res.users', string='요청자', readonly=True, copy=False,
                                   default=lambda self: self.env.user, index=True)
    request_date = fields.Date('요청일', readonly=True, copy=False,
                               default=fields.Date.context_today)
    maintenance_type = fields.Selection([
        ('corrective', '고장 정비'),
        ('preventive', '예방 정비'),
    ], string='유형', required=True, default='corrective')
    priority = fields.Selection([
        ('normal', '보통'),
        ('high', '높음'),
        ('urgent', '긴급'),
    ], string='우선순위', required=True, default='normal')
    symptom = fields.Text('증상')
    technician_id = fields.Many2one(
        'res.users', string='배정 정비원', copy=False, index=True, ondelete='restrict',
        domain=lambda self: _technician_domain(self))
    state = fields.Selection([
        ('request', '요청'),
        ('accepted', '접수'),
        ('in_progress', '작업 중'),
        ('done', '완료'),
        ('rejected', '반려'),
    ], string='상태', required=True, default='request', readonly=True, copy=False,
        group_expand='_read_group_expand_full')
    reject_reason = fields.Text('반려 사유', readonly=True, copy=False)
    done_date = fields.Date('완료일', readonly=True, copy=False)
    work_log_ids = fields.One2many('mes.maintenance.work.log', 'request_id', string='작업 기록')
    cost_ids = fields.One2many('mes.maintenance.cost', 'request_id', string='비용')
    total_hours = fields.Float('총 소요 시간', compute='_compute_totals', store=True)
    total_cost = fields.Monetary('총 비용', compute='_compute_totals', store=True,
                                 currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='통화', compute='_compute_currency_id')

    # 화면 제어용
    can_edit_request = fields.Boolean('요청 수정 가능', compute='_compute_permissions')
    can_work = fields.Boolean('작업 가능', compute='_compute_permissions')
    is_manager = fields.Boolean('관리자 여부', compute='_compute_permissions')

    def _compute_currency_id(self):
        for request in self:
            request.currency_id = self.env.company.currency_id

    @api.depends('work_log_ids.hours', 'cost_ids.amount')
    def _compute_totals(self):
        for request in self:
            request.total_hours = sum(request.work_log_ids.mapped('hours'))
            request.total_cost = sum(request.cost_ids.mapped('amount'))

    @api.depends_context('uid')
    @api.depends('state', 'requester_id', 'technician_id')
    def _compute_permissions(self):
        is_manager = self._is_manager()
        user = self.env.user
        for request in self:
            request.is_manager = is_manager
            request.can_edit_request = request.state == 'request' and (
                is_manager or request.requester_id == user)
            request.can_work = request.state in WORK_STATES and (
                is_manager or request.technician_id == user)

    # ------------------------------------------------------------------
    # 권한 도우미
    # ------------------------------------------------------------------
    def _is_manager(self):
        return self.env.su or self.env.user.has_group(GROUP_MANAGER)

    def _check_can_work(self):
        """배정 정비원 또는 관리자만 작업할 수 있다."""
        if self._is_manager():
            return
        user = self.env.user
        for request in self:
            if request.technician_id != user:
                raise AccessError(f'{request.name}: 배정된 정비원 또는 관리자만 할 수 있습니다.')

    def _check_manager(self):
        if not self._is_manager():
            raise AccessError('정비 관리자만 할 수 있습니다.')

    def _set_state(self, vals):
        """동작을 통해서만 상태를 바꾼다(아래 write 재정의를 거치지 않음)."""
        return super(MesMaintenanceRequest, self.sudo()).write(vals)

    # ------------------------------------------------------------------
    # 제약
    # ------------------------------------------------------------------
    @api.constrains('technician_id')
    def _check_technician(self):
        group = self.env.ref(GROUP_TECHNICIAN)
        for request in self:
            if request.technician_id and group not in request.technician_id.sudo().all_group_ids:
                raise ValidationError('배정 정비원은 정비원 그룹의 사용자여야 합니다.')

    @api.constrains('equipment_id')
    def _check_equipment_active(self):
        for request in self:
            if not request.equipment_id.sudo().active:
                raise ValidationError('사용 중인 설비만 선택할 수 있습니다.')

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            is_manager = self._is_manager()
            for vals in vals_list:
                for field in ('state', 'reject_reason', 'done_date', 'name', 'request_date'):
                    vals.pop(field, None)
                vals['requester_id'] = self.env.uid
                if vals.get('technician_id') and not is_manager:
                    raise AccessError('배정 정비원은 정비 관리자만 정할 수 있습니다.')
                if vals.get('work_log_ids') or vals.get('cost_ids'):
                    raise UserError('작업 기록과 비용은 접수된 요청에만 입력할 수 있습니다.')
        sequence = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            vals['name'] = sequence.next_by_code('mes.maintenance.request') or '새 요청'
            vals['state'] = 'request'
        return super().create(vals_list)

    def write(self, vals):
        if 'state' in vals:
            raise UserError('상태는 접수·반려·작업 시작·완료 동작으로만 바꿀 수 있습니다.')
        if not self.env.su:
            self._check_write_allowed(vals)
        return super().write(vals)

    def _check_write_allowed(self, vals):
        fields_set = set(vals)
        other = fields_set - REQUEST_EDIT_FIELDS - WORK_FIELDS - {'technician_id'}
        if other:
            labels = ', '.join(sorted(
                self._fields[f].string if f in self._fields else f for f in other))
            raise UserError(f'직접 수정할 수 없는 항목입니다: {labels}')
        is_manager = self._is_manager()
        user = self.env.user
        for request in self:
            if request.state in CLOSED_STATES:
                raise UserError(f'{request.name}: 완료되거나 반려된 요청은 수정할 수 없습니다.')
            if fields_set & REQUEST_EDIT_FIELDS:
                if request.state != 'request':
                    raise UserError(
                        f'{request.name}: 설비·유형·우선순위·증상은 요청 상태에서만 고칠 수 있습니다.')
                if not is_manager and request.requester_id != user:
                    raise AccessError(f'{request.name}: 요청을 만든 사람 또는 관리자만 고칠 수 있습니다.')
            if 'technician_id' in fields_set:
                if not is_manager:
                    raise AccessError('배정 정비원은 정비 관리자만 바꿀 수 있습니다.')
                if request.state not in OPEN_STATES:
                    raise UserError(f'{request.name}: 이 상태에서는 배정 정비원을 바꿀 수 없습니다.')
                if request.state in WORK_STATES and not vals.get('technician_id'):
                    raise UserError(f'{request.name}: 접수 이후에는 배정 정비원을 비울 수 없습니다.')
            if fields_set & WORK_FIELDS:
                if request.state not in WORK_STATES:
                    raise UserError(
                        f'{request.name}: 작업 기록과 비용은 접수·작업 중 상태에서만 입력할 수 있습니다.')
                if not is_manager and request.technician_id != user:
                    raise AccessError(
                        f'{request.name}: 배정된 정비원 또는 관리자만 작업 기록과 비용을 입력할 수 있습니다.')

    @api.ondelete(at_uninstall=False)
    def _unlink_except_not_request(self):
        for request in self:
            if request.state != 'request':
                raise UserError(f'{request.name}: 요청 상태의 요청만 삭제할 수 있습니다.')
        if not self._is_manager():
            if any(request.requester_id != self.env.user for request in self):
                raise AccessError('요청을 만든 사람 또는 관리자만 삭제할 수 있습니다.')

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------
    def action_accept(self):
        self._check_manager()
        for request in self:
            if request.state != 'request':
                raise UserError(f'{request.name}: 요청 상태에서만 접수할 수 있습니다.')
            if not request.technician_id:
                raise UserError(f'{request.name}: 배정 정비원을 먼저 정하세요.')
        self._set_state({'state': 'accepted'})
        return True

    def action_reject(self):
        self.ensure_one()
        self._check_manager()
        if self.state != 'request':
            raise UserError('요청 상태에서만 반려할 수 있습니다.')
        return {
            'type': 'ir.actions.act_window',
            'name': '반려 사유',
            'res_model': 'mes.maintenance.reject.wizard',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'new',
            'context': {'default_request_id': self.id},
        }

    def _do_reject(self, reason):
        self._check_manager()
        reason = (reason or '').strip()
        if not reason:
            raise UserError('반려 사유를 입력해야 합니다.')
        for request in self:
            if request.state != 'request':
                raise UserError(f'{request.name}: 요청 상태에서만 반려할 수 있습니다.')
        self._set_state({'state': 'rejected', 'reject_reason': reason})
        return True

    def action_start(self):
        for request in self:
            if request.state != 'accepted':
                raise UserError(f'{request.name}: 접수 상태에서만 작업을 시작할 수 있습니다.')
        self._check_can_work()
        self._set_state({'state': 'in_progress'})
        return True

    def action_done(self):
        for request in self:
            if request.state != 'in_progress':
                raise UserError(f'{request.name}: 작업 중 상태에서만 완료할 수 있습니다.')
            if not request.sudo().work_log_ids:
                raise UserError(f'{request.name}: 작업 기록이 하나 이상 있어야 완료할 수 있습니다.')
        self._check_can_work()
        today = fields.Date.context_today(self)
        self._set_state({'state': 'done', 'done_date': today})
        for request in self.sudo():
            if request.maintenance_type == 'preventive':
                request.equipment_id._update_next_preventive_date(today)
        return True
