from odoo import api, fields, models
from odoo.fields import Command
from odoo.exceptions import AccessError, UserError, ValidationError

GROUP_WORKER = 'mes_work_order.group_mes_worker'
GROUP_MANAGER = 'mes_work_order.group_mes_manager'


def _worker_domain(model):
    group = model.env.ref(GROUP_WORKER, raise_if_not_found=False)
    return [('all_group_ids', 'in', group.ids if group else [])]


class MesWorkOrderAssignWizard(models.TransientModel):
    _name = 'mes.work.order.assign.wizard'
    _description = '일괄 담당자 지정'

    work_order_ids = fields.Many2many(
        'mes.work.order', string='작업지시', required=True)
    user_id = fields.Many2one(
        'res.users', string='새 담당자', required=True,
        domain=lambda self: _worker_domain(self))

    @api.model
    def _check_manager(self):
        if not (self.env.is_superuser() or self.env.user.has_group(GROUP_MANAGER)):
            raise AccessError('일괄 담당자 지정은 관리자만 할 수 있습니다.')

    @api.model
    def default_get(self, fields_list):
        self._check_manager()
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids')
        if (
            'work_order_ids' in fields_list
            and self.env.context.get('active_model') == 'mes.work.order'
            and active_ids
        ):
            res['work_order_ids'] = [Command.set(active_ids)]
        return res

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager()
        return super().create(vals_list)

    def _check_targets(self):
        for wizard in self:
            closed = wizard.work_order_ids.filtered(lambda o: o.state in ('done', 'cancel'))
            if closed:
                raise UserError(
                    '완료되거나 취소된 작업지시는 담당자를 바꿀 수 없습니다: %s'
                    % ', '.join(closed.mapped('name')))
            if not wizard.user_id.has_group(GROUP_WORKER):
                raise ValidationError(
                    '새 담당자는 작업자 그룹의 사용자여야 합니다: %s' % wizard.user_id.display_name)

    def action_apply(self):
        self._check_manager()
        self._check_targets()
        for wizard in self:
            wizard.work_order_ids.write({'user_id': wizard.user_id.id})
        return {'type': 'ir.actions.act_window_close'}
