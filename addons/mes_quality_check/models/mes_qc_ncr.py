from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from .mes_qc_common import GROUP_INSPECTOR, internal_env, is_internal, is_manager


class MesQcNcr(models.Model):
    _name = 'mes.qc.ncr'
    _description = '부적합 보고서'
    _order = 'id desc'

    # 사용자가 쓸 수 있는 필드. 나머지는 코드로만 바뀐다.
    _USER_WRITABLE_FIELDS = {'cause', 'action_taken', 'user_id'}

    name = fields.Char(string='번호', required=True, readonly=True, copy=False, default='새 보고서')
    inspection_id = fields.Many2one(
        'mes.qc.inspection', string='원래 검사', required=True, readonly=True,
        index=True, ondelete='restrict')
    target = fields.Char(related='inspection_id.target', string='검사 대상')
    partner_id = fields.Many2one(related='inspection_id.partner_id', string='공급처')
    inspection_date = fields.Date(related='inspection_id.date', string='검사일')
    summary = fields.Text(string='불합격 항목 요약', readonly=True)
    cause = fields.Text(string='원인')
    action_taken = fields.Text(string='조치 내용')
    user_id = fields.Many2one(
        'res.users', string='담당자', required=True, index=True, ondelete='restrict',
        domain=lambda self: [('share', '=', False),
                             ('all_group_ids', 'in', self.env.ref(GROUP_INSPECTOR).id)])
    state = fields.Selection(
        [('open', '열림'), ('in_progress', '조치 중'), ('closed', '종결')],
        string='상태', default='open', required=True, readonly=True, copy=False, index=True)
    is_manager = fields.Boolean(string='관리자 여부', compute='_compute_permissions')
    can_edit = fields.Boolean(string='원인·조치 입력 가능', compute='_compute_permissions')

    _inspection_unique = models.Constraint(
        'unique(inspection_id)',
        '한 검사에는 부적합 보고서가 최대 하나입니다.',
    )

    @api.depends_context('uid')
    @api.depends('state', 'user_id')
    def _compute_permissions(self):
        manager = is_manager(self.env)
        for ncr in self:
            ncr.is_manager = manager
            ncr.can_edit = ncr.state in ('open', 'in_progress') and (
                manager or ncr.user_id == self.env.user)

    @api.constrains('user_id')
    def _check_user_group(self):
        group = self.env.ref(GROUP_INSPECTOR)
        for ncr in self:
            if group not in ncr.user_id.sudo().all_group_ids:
                raise ValidationError(_("담당자는 검사원 그룹의 사용자여야 합니다."))

    def _check_assignee_or_manager(self, action_label):
        if self.env.su or is_manager(self.env):
            return
        for ncr in self:
            if ncr.user_id != self.env.user:
                raise AccessError(_(
                    "부적합 보고서 '%(name)s'의 담당자가 아니므로 %(action)s 수 없습니다.",
                    name=ncr.name, action=action_label))

    # ------------------------------------------------------------------
    # 생성: 검사 완료 시 코드로만 만든다.
    # ------------------------------------------------------------------
    @api.model
    def _create_from_inspection(self, inspection):
        inspection.ensure_one()
        existing = self.sudo().search([('inspection_id', '=', inspection.id)], limit=1)
        if existing:
            return existing
        failed = inspection.line_ids.filtered(lambda l: l.result == 'fail')
        summary_lines = []
        for line in failed:
            uom = line.uom or ''
            summary_lines.append(_(
                "- %(item)s: 측정값 %(value)s%(uom)s (기준 %(low)s ~ %(high)s%(uom)s)",
                item=line.item_id.name,
                value=line.value_input.strip() if line.value_input else line.value,
                uom=(' ' + uom) if uom else '',
                low=line.lower_limit,
                high=line.upper_limit,
            ))
        return internal_env(self.sudo()).create({
            'inspection_id': inspection.id,
            'user_id': inspection.inspector_id.id,
            'summary': '\n'.join(summary_lines),
        })

    @api.model_create_multi
    def create(self, vals_list):
        if not is_internal(self):
            raise UserError(_("부적합 보고서는 불합격 검사를 완료할 때 자동으로만 만들어집니다."))
        for vals in vals_list:
            vals['state'] = 'open'
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code('mes.qc.ncr') or '새 보고서'
        return super().create(vals_list)

    def write(self, vals):
        if not is_internal(self):
            if 'state' in vals:
                raise UserError(_("상태는 직접 바꿀 수 없습니다. [조치 시작]·[종결] 동작을 사용하십시오."))
            forbidden = set(vals) - self._USER_WRITABLE_FIELDS
            if forbidden:
                raise UserError(_("부적합 보고서의 번호·원래 검사·요약은 바꿀 수 없습니다."))
            if self.filtered(lambda r: r.state == 'closed'):
                raise UserError(_("종결된 부적합 보고서는 고칠 수 없습니다."))
            if 'user_id' in vals and not (self.env.su or is_manager(self.env)):
                raise AccessError(_("담당자는 관리자만 바꿀 수 있습니다."))
            self._check_assignee_or_manager(_("고칠"))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_never(self):
        raise UserError(_("부적합 보고서는 삭제할 수 없습니다."))

    def copy(self, default=None):
        raise UserError(_("부적합 보고서는 복제할 수 없습니다."))

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------
    def action_start(self):
        for ncr in self:
            if ncr.state != 'open':
                raise UserError(_("열림 상태의 보고서만 조치를 시작할 수 있습니다."))
            ncr._check_assignee_or_manager(_("조치를 시작할"))
            ncr.check_access('write')
            internal_env(ncr).write({'state': 'in_progress'})
        return True

    def action_close(self):
        if not is_manager(self.env):
            raise AccessError(_("부적합 보고서는 품질 관리자만 종결할 수 있습니다."))
        for ncr in self:
            if ncr.state != 'in_progress':
                raise UserError(_("조치 중 상태의 보고서만 종결할 수 있습니다."))
            if not (ncr.cause or '').strip() or not (ncr.action_taken or '').strip():
                raise UserError(_("원인과 조치 내용을 모두 입력해야 종결할 수 있습니다."))
            ncr.check_access('write')
            internal_env(ncr).write({'state': 'closed'})
        return True

    def action_open_inspection(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('검사'),
            'res_model': 'mes.qc.inspection',
            'res_id': self.inspection_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }
