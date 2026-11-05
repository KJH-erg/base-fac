from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

GROUP_WORKER = 'mes_work_order.group_mes_worker'
GROUP_MANAGER = 'mes_work_order.group_mes_manager'

OPEN_STATES = ('draft', 'confirmed', 'in_progress', 'on_hold')
EDITABLE_STATES = ('draft', 'confirmed')
RUNNING_STATES = ('in_progress', 'on_hold')
CLOSED_STATES = ('done', 'cancel')

# 동작(버튼)으로만 바뀌는 항목: 사용자가 직접 쓸 수 없다.
PROTECTED_FIELDS = {
    'name', 'state', 'is_delayed',
    'date_actual_start', 'date_actual_end',
    'duration_hours', 'progress',
}
# 진행 중·보류일 때 관리자가 고칠 수 있는 항목
MANAGER_RUNNING_FIELDS = {'date_end', 'user_id', 'note'}
# 담당 작업자가 고칠 수 있는 항목
ASSIGNEE_FIELDS = {'note'}


def _worker_domain(model):
    group = model.env.ref(GROUP_WORKER, raise_if_not_found=False)
    return [('all_group_ids', 'in', group.ids if group else [])]


class MesWorkOrder(models.Model):
    _name = 'mes.work.order'
    _description = '작업지시'
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='번호', required=True, readonly=True, copy=False,
        default='새 작업지시', index=True)
    title = fields.Char(string='제목', required=True)
    product_name = fields.Char(string='대상 품목')
    quantity = fields.Float(string='수량', digits=(16, 2), default=0.0)
    user_id = fields.Many2one(
        'res.users', string='담당자', index=True,
        domain=lambda self: _worker_domain(self))
    date_start = fields.Date(string='계획 시작일')
    date_end = fields.Date(string='계획 종료일')
    date_actual_start = fields.Datetime(string='실제 착수 시각', readonly=True, copy=False)
    date_actual_end = fields.Datetime(string='실제 완료 시각', readonly=True, copy=False)
    duration_hours = fields.Float(
        string='실제 소요 시간(시간)', compute='_compute_duration_hours',
        store=True, digits=(16, 2))
    state = fields.Selection(
        [
            ('draft', '초안'),
            ('confirmed', '확정'),
            ('in_progress', '진행 중'),
            ('on_hold', '보류'),
            ('done', '완료'),
            ('cancel', '취소'),
        ],
        string='상태', required=True, default='draft', readonly=True,
        copy=False, index=True, group_expand=True)
    note = fields.Text(string='메모')
    is_delayed = fields.Boolean(string='지연', readonly=True, copy=False, index=True)
    step_ids = fields.One2many(
        'mes.work.order.step', 'work_order_id', string='공정 단계', copy=True)
    progress = fields.Float(
        string='진행률(%)', compute='_compute_progress', store=True, digits=(16, 0))

    is_manager = fields.Boolean(compute='_compute_user_flags')
    is_assignee = fields.Boolean(compute='_compute_user_flags')

    _date_check = models.Constraint(
        'CHECK(date_start IS NULL OR date_end IS NULL OR date_end >= date_start)',
        '계획 종료일은 계획 시작일보다 앞설 수 없습니다.',
    )

    # ------------------------------------------------------------------
    # 계산 항목
    # ------------------------------------------------------------------
    @api.depends('date_actual_start', 'date_actual_end')
    def _compute_duration_hours(self):
        for rec in self:
            if rec.date_actual_start and rec.date_actual_end:
                delta = rec.date_actual_end - rec.date_actual_start
                rec.duration_hours = delta.total_seconds() / 3600.0
            else:
                rec.duration_hours = 0.0

    @api.depends('step_ids', 'step_ids.is_done')
    def _compute_progress(self):
        for rec in self:
            total = len(rec.step_ids)
            done = len(rec.step_ids.filtered('is_done'))
            rec.progress = (done * 100.0 / total) if total else 0.0

    @api.depends('user_id')
    @api.depends_context('uid')
    def _compute_user_flags(self):
        is_manager = self.env.user.has_group(GROUP_MANAGER)
        for rec in self:
            rec.is_manager = is_manager
            rec.is_assignee = bool(rec.user_id) and rec.user_id == self.env.user

    # ------------------------------------------------------------------
    # 제약
    # ------------------------------------------------------------------
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for rec in self:
            if rec.date_start and rec.date_end and rec.date_end < rec.date_start:
                raise ValidationError('계획 종료일은 계획 시작일보다 앞설 수 없습니다.')

    @api.constrains('user_id')
    def _check_user_id(self):
        for rec in self:
            if rec.user_id and not rec.user_id.has_group(GROUP_WORKER):
                raise ValidationError(
                    '담당자는 작업자 그룹의 사용자여야 합니다: %s' % rec.user_id.display_name)

    # ------------------------------------------------------------------
    # 권한 도우미
    # ------------------------------------------------------------------
    def _is_manager(self):
        return self.env.is_superuser() or self.env.user.has_group(GROUP_MANAGER)

    def _check_manager(self):
        if not self._is_manager():
            raise AccessError('이 작업은 관리자만 할 수 있습니다.')

    def _check_assignee_or_manager(self):
        if self._is_manager():
            return
        for rec in self:
            if not rec.user_id or rec.user_id != self.env.user:
                raise AccessError(
                    '담당자 본인 또는 관리자만 할 수 있습니다: %s' % rec.name)

    def _check_state(self, allowed, action_label):
        for rec in self:
            if rec.state not in allowed:
                raise UserError(
                    '%s 상태의 작업지시는 [%s]할 수 없습니다: %s'
                    % (dict(rec._fields['state'].selection).get(rec.state), action_label, rec.name))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.is_superuser():
            self._check_manager()
            for vals in vals_list:
                forbidden = (set(vals) & PROTECTED_FIELDS) - {'state'}
                if forbidden or vals.get('state', 'draft') != 'draft':
                    raise UserError('번호, 상태, 지연, 실제 착수·완료 시각은 직접 입력할 수 없습니다.')
        seq = self.env['ir.sequence'].sudo()
        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == '새 작업지시':
                vals['name'] = seq.next_by_code('mes.work.order') or '새 작업지시'
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.is_superuser():
            self._check_write_allowed(vals)
        vals = dict(vals)
        if vals.get('date_end'):
            today = fields.Date.context_today(self)
            if fields.Date.to_date(vals['date_end']) >= today:
                vals['is_delayed'] = False
        return super().write(vals)

    def _check_write_allowed(self, vals):
        fnames = set(vals)
        protected = fnames & PROTECTED_FIELDS
        if protected:
            raise UserError(
                '다음 항목은 직접 고칠 수 없습니다(상태는 동작 버튼으로만 바뀝니다): %s'
                % ', '.join(sorted(self._fields[f].string for f in protected)))
        is_manager = self._is_manager()
        for rec in self:
            if rec.state in CLOSED_STATES:
                raise UserError('완료되거나 취소된 작업지시는 고칠 수 없습니다: %s' % rec.name)
            if is_manager:
                if rec.state in EDITABLE_STATES:
                    continue
                allowed = MANAGER_RUNNING_FIELDS
            elif rec.user_id and rec.user_id == self.env.user:
                allowed = ASSIGNEE_FIELDS
            else:
                raise AccessError('작업지시를 고칠 권한이 없습니다: %s' % rec.name)
            not_allowed = fnames - allowed
            if not_allowed:
                raise UserError(
                    '현재 상태(%s)에서는 다음 항목을 고칠 수 없습니다: %s'
                    % (dict(rec._fields['state'].selection).get(rec.state),
                       ', '.join(sorted(rec._fields[f].string for f in not_allowed))))

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if not self.env.is_superuser():
            self._check_manager()
        for rec in self:
            if rec.state != 'draft':
                raise UserError('초안 상태의 작업지시만 지울 수 있습니다: %s' % rec.name)

    # ------------------------------------------------------------------
    # 상태 동작
    # ------------------------------------------------------------------
    def action_confirm(self):
        self._check_manager()
        self._check_state(('draft',), '확정')
        for rec in self:
            problems = []
            if rec.quantity <= 0:
                problems.append('수량이 0보다 커야 합니다.')
            if not rec.date_start or not rec.date_end:
                problems.append('계획 시작일과 계획 종료일을 입력해야 합니다.')
            if not rec.step_ids:
                problems.append('공정 단계가 하나 이상 있어야 합니다.')
            if problems:
                raise UserError('[%s] 확정할 수 없습니다.\n%s' % (rec.name, '\n'.join(problems)))
        self.sudo().write({'state': 'confirmed'})
        return True

    def action_start(self):
        self._check_state(('confirmed',), '착수')
        self._check_assignee_or_manager()
        self.sudo().write({
            'state': 'in_progress',
            'date_actual_start': fields.Datetime.now(),
        })
        return True

    def action_hold(self):
        self._check_state(('in_progress',), '보류')
        self._check_assignee_or_manager()
        self.sudo().write({'state': 'on_hold'})
        return True

    def action_resume(self):
        self._check_state(('on_hold',), '재개')
        self._check_assignee_or_manager()
        self.sudo().write({'state': 'in_progress'})
        return True

    def action_done(self):
        self._check_state(('in_progress',), '완료')
        self._check_assignee_or_manager()
        for rec in self:
            remaining = rec.step_ids.filtered(lambda s: not s.is_done)
            if remaining:
                raise UserError(
                    '[%s] 완료되지 않은 공정 단계가 있어 완료할 수 없습니다.\n남은 단계: %s'
                    % (rec.name, ', '.join(remaining.sorted('sequence').mapped('name'))))
        self.sudo().write({
            'state': 'done',
            'date_actual_end': fields.Datetime.now(),
            'is_delayed': False,
        })
        return True

    def action_cancel(self):
        self._check_manager()
        self._check_state(OPEN_STATES, '취소')
        self.sudo().write({'state': 'cancel', 'is_delayed': False})
        return True

    # ------------------------------------------------------------------
    # 자동 처리
    # ------------------------------------------------------------------
    @api.model
    def _cron_mark_delayed(self):
        today = fields.Date.context_today(self)
        orders = self.sudo().search([
            ('state', 'in', OPEN_STATES),
            ('date_end', '!=', False),
            ('date_end', '<', today),
            ('is_delayed', '=', False),
        ])
        if orders:
            orders.write({'is_delayed': True})
        return True
