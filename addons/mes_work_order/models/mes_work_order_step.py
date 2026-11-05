from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError

GROUP_MANAGER = 'mes_work_order.group_mes_manager'

STRUCTURE_FIELDS = {'name', 'sequence', 'work_order_id'}
DONE_FIELDS = {'is_done'}


class MesWorkOrderStep(models.Model):
    _name = 'mes.work.order.step'
    _description = '공정 단계'
    _order = 'work_order_id, sequence, id'

    work_order_id = fields.Many2one(
        'mes.work.order', string='작업지시', required=True,
        ondelete='cascade', index=True)
    sequence = fields.Integer(string='순서', default=10)
    name = fields.Char(string='단계 이름', required=True)
    is_done = fields.Boolean(string='완료', readonly=True, copy=False)
    done_date = fields.Datetime(string='완료 시각', readonly=True, copy=False)
    work_order_state = fields.Selection(
        related='work_order_id.state', string='작업지시 상태')

    # ------------------------------------------------------------------
    # 권한 도우미
    # ------------------------------------------------------------------
    def _is_manager(self):
        return self.env.is_superuser() or self.env.user.has_group(GROUP_MANAGER)

    @api.model
    def _check_structure_allowed(self, orders):
        """공정 단계 추가·삭제·순서·이름 변경: 관리자, 초안·확정 상태만."""
        if self.env.is_superuser():
            return
        if not self._is_manager():
            raise AccessError('공정 단계 편성은 관리자만 할 수 있습니다.')
        for order in orders:
            if order.state not in ('draft', 'confirmed'):
                raise UserError(
                    '초안·확정 상태에서만 공정 단계를 추가·삭제·변경할 수 있습니다: %s' % order.name)

    def _check_done_allowed(self):
        """완료 표시·되돌리기: 진행 중 상태, 담당자 본인 또는 관리자."""
        if self.env.is_superuser():
            return
        is_manager = self._is_manager()
        for step in self:
            order = step.work_order_id
            if order.state != 'in_progress':
                raise UserError(
                    '진행 중인 작업지시에서만 공정 단계를 완료 표시하거나 되돌릴 수 있습니다: %s' % order.name)
            if not is_manager and (not order.user_id or order.user_id != self.env.user):
                raise AccessError(
                    '담당자 본인 또는 관리자만 공정 단계를 완료 표시할 수 있습니다: %s' % order.name)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.is_superuser():
            for vals in vals_list:
                if vals.get('is_done') or vals.get('done_date'):
                    raise UserError('공정 단계는 진행 중인 작업지시에서만 완료 표시할 수 있습니다.')
            order_ids = {vals.get('work_order_id') for vals in vals_list if vals.get('work_order_id')}
            self._check_structure_allowed(self.env['mes.work.order'].browse(list(order_ids)))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.is_superuser():
            fnames = set(vals)
            if 'done_date' in fnames:
                raise UserError('완료 시각은 직접 고칠 수 없습니다.')
            unknown = fnames - STRUCTURE_FIELDS - DONE_FIELDS
            if unknown:
                raise UserError('공정 단계의 다음 항목은 고칠 수 없습니다: %s' % ', '.join(sorted(unknown)))
            if fnames & STRUCTURE_FIELDS:
                orders = self.work_order_id
                if vals.get('work_order_id'):
                    orders |= self.env['mes.work.order'].browse(vals['work_order_id'])
                self._check_structure_allowed(orders)
            if fnames & DONE_FIELDS:
                self._check_done_allowed()
        vals = dict(vals)
        if 'is_done' in vals and 'done_date' not in vals:
            vals['done_date'] = fields.Datetime.now() if vals['is_done'] else False
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_check_state(self):
        self._check_structure_allowed(self.work_order_id)

    # ------------------------------------------------------------------
    # 버튼
    # ------------------------------------------------------------------
    def action_mark_done(self):
        steps = self.filtered(lambda s: not s.is_done)
        (steps or self)._check_done_allowed()
        if steps:
            steps.write({'is_done': True})
        return True

    def action_mark_undone(self):
        steps = self.filtered('is_done')
        (steps or self)._check_done_allowed()
        if steps:
            steps.write({'is_done': False})
        return True
