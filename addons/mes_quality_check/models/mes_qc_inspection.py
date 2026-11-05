from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare

from .mes_qc_common import GROUP_INSPECTOR, internal_env, is_internal, is_manager

RESULT_SELECTION = [
    ('pass', '합격'),
    ('fail', '불합격'),
]


class MesQcInspection(models.Model):
    _name = 'mes.qc.inspection'
    _description = '검사'
    _order = 'date desc, id desc'

    # 사용자가 직접 바꿀 수 없는 필드
    _PROTECTED_FIELDS = {'state', 'result', 'name'}

    name = fields.Char(string='번호', required=True, readonly=True, copy=False, default='새 검사')
    target = fields.Char(string='검사 대상', required=True, help='검사할 로트·품목')
    partner_id = fields.Many2one('res.partner', string='공급처', index=True, ondelete='restrict')
    inspector_id = fields.Many2one(
        'res.users', string='검사원', required=True, index=True, ondelete='restrict',
        default=lambda self: self.env.user,
        domain=lambda self: [('share', '=', False),
                             ('all_group_ids', 'in', self.env.ref(GROUP_INSPECTOR).id)])
    date = fields.Date(string='검사일', required=True, default=fields.Date.context_today)
    line_ids = fields.One2many('mes.qc.inspection.line', 'inspection_id', string='측정 줄')
    result = fields.Selection(
        RESULT_SELECTION, string='전체 판정', compute='_compute_result', store=True, readonly=True)
    state = fields.Selection(
        [('draft', '초안'), ('done', '검사 완료')], string='상태',
        default='draft', required=True, readonly=True, copy=False, index=True)
    ncr_ids = fields.One2many('mes.qc.ncr', 'inspection_id', string='부적합 보고서 목록', readonly=True)
    ncr_id = fields.Many2one('mes.qc.ncr', string='부적합 보고서', compute='_compute_ncr_id')
    can_edit = fields.Boolean(string='편집 가능', compute='_compute_can_edit')

    @api.depends('line_ids.result')
    def _compute_result(self):
        for inspection in self:
            results = inspection.line_ids.mapped('result')
            if 'fail' in results:
                inspection.result = 'fail'
            elif 'pass' in results:
                inspection.result = 'pass'
            else:
                inspection.result = False

    @api.depends('ncr_ids')
    def _compute_ncr_id(self):
        for inspection in self:
            inspection.ncr_id = inspection.ncr_ids[:1]

    @api.depends_context('uid')
    @api.depends('state', 'inspector_id')
    def _compute_can_edit(self):
        manager = is_manager(self.env)
        for inspection in self:
            inspection.can_edit = inspection.state == 'draft' and (
                manager or inspection.inspector_id == self.env.user)

    # ------------------------------------------------------------------
    # 제약·권한 확인
    # ------------------------------------------------------------------
    @api.constrains('inspector_id')
    def _check_inspector_group(self):
        group = self.env.ref(GROUP_INSPECTOR)
        for inspection in self:
            if group not in inspection.inspector_id.sudo().all_group_ids:
                raise ValidationError(_("검사원은 검사원 그룹의 사용자여야 합니다."))

    def _check_owner_or_manager(self, action_label):
        if self.env.su or is_manager(self.env):
            return
        for inspection in self:
            if inspection.inspector_id != self.env.user:
                raise AccessError(_(
                    "검사 '%(name)s'의 검사원이 아니므로 %(action)s 수 없습니다.",
                    name=inspection.name, action=action_label))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        internal = is_internal(self)
        manager = self.env.su or is_manager(self.env)
        for vals in vals_list:
            if not internal:
                if vals.get('state', 'draft') != 'draft':
                    raise UserError(_("검사는 초안 상태로만 만들 수 있습니다. 상태는 [검사 완료] 동작으로만 바뀝니다."))
                for fname in self._PROTECTED_FIELDS:
                    vals.pop(fname, None)
            if not manager and vals.get('inspector_id', self.env.uid) != self.env.uid:
                raise AccessError(_("다른 검사원을 검사원으로 지정한 검사는 관리자만 만들 수 있습니다."))
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code('mes.qc.inspection') or '새 검사'
        return super().create(vals_list)

    def write(self, vals):
        if not is_internal(self):
            if self._PROTECTED_FIELDS.intersection(vals):
                raise UserError(_("번호·상태·판정은 직접 바꿀 수 없습니다. 상태는 [검사 완료] 동작으로만 바뀝니다."))
            if self.filtered(lambda r: r.state != 'draft'):
                raise UserError(_("완료된 검사는 고칠 수 없습니다."))
            self._check_owner_or_manager(_("고칠"))
            if ('inspector_id' in vals and not (self.env.su or is_manager(self.env))
                    and vals['inspector_id'] != self.env.uid):
                raise AccessError(_("검사원은 관리자만 다른 사람으로 바꿀 수 있습니다."))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        if self.filtered(lambda r: r.state != 'draft'):
            raise UserError(_("완료된 검사는 삭제할 수 없습니다. 초안 검사만 삭제할 수 있습니다."))
        self._check_owner_or_manager(_("삭제할"))

    def copy(self, default=None):
        raise UserError(_("검사는 복제할 수 없습니다. 새로 만드십시오."))

    # ------------------------------------------------------------------
    # 동작
    # ------------------------------------------------------------------
    def action_done(self):
        for inspection in self:
            if inspection.state != 'draft':
                raise UserError(_("초안 상태의 검사만 완료할 수 있습니다."))
            inspection._check_owner_or_manager(_("완료할"))
            inspection.check_access('write')
            if not inspection.line_ids:
                raise UserError(_("측정 줄이 하나 이상 있어야 검사를 완료할 수 있습니다."))
            missing = inspection.line_ids.filtered(lambda l: not l.has_value)
            if missing:
                raise UserError(_(
                    "측정값을 입력하지 않은 줄이 있습니다: %s",
                    ', '.join(missing.mapped('item_id.name'))))
            internal_env(inspection).write({'state': 'done'})
            if inspection.result == 'fail' and not inspection.sudo().ncr_ids:
                self.env['mes.qc.ncr'].sudo()._create_from_inspection(inspection)
        return True

    def action_open_ncr(self):
        self.ensure_one()
        if not self.ncr_id:
            raise UserError(_("연결된 부적합 보고서가 없습니다."))
        return {
            'type': 'ir.actions.act_window',
            'name': _('부적합 보고서'),
            'res_model': 'mes.qc.ncr',
            'res_id': self.ncr_id.id,
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
        }


class MesQcInspectionLine(models.Model):
    _name = 'mes.qc.inspection.line'
    _description = '측정 줄'
    _order = 'inspection_id, sequence, id'

    # 사용자가 직접 쓸 수 없는 필드(코드가 채우거나 계산함)
    _PROTECTED_FIELDS = {'result', 'lower_limit', 'upper_limit', 'value', 'has_value'}

    sequence = fields.Integer(string='순서', default=10)
    inspection_id = fields.Many2one(
        'mes.qc.inspection', string='검사', required=True, index=True, ondelete='cascade')
    inspection_state = fields.Selection(related='inspection_id.state', string='검사 상태')
    item_id = fields.Many2one(
        'mes.qc.item', string='검사 항목', required=True, index=True, ondelete='restrict',
        domain=[('active', '=', True)])
    uom = fields.Char(related='item_id.uom', string='단위')
    # 기준값은 줄에 복사해 둔다. 초안 검사일 때만 항목 기준 변경을 따라가고,
    # 완료된 검사는 완료 시점의 기준(따라서 판정)을 유지한다.
    lower_limit = fields.Float(string='하한값', digits=(16, 4), readonly=True)
    upper_limit = fields.Float(string='상한값', digits=(16, 4), readonly=True)
    # 측정값: 입력하지 않은 상태(빈칸)와 0을 구분하기 위해 글자로 입력받아 숫자로 바꾼다.
    value_input = fields.Char(string='측정값')
    value = fields.Float(
        string='측정값(수치)', digits=(16, 4), compute='_compute_value', store=True, readonly=True)
    has_value = fields.Boolean(string='측정함', compute='_compute_value', store=True, readonly=True)
    result = fields.Selection(
        RESULT_SELECTION, string='판정', compute='_compute_result', store=True, readonly=True)

    _item_unique_per_inspection = models.Constraint(
        'unique(inspection_id, item_id)',
        '한 검사에 같은 검사 항목을 두 번 넣을 수 없습니다.',
    )

    @staticmethod
    def _parse_value(text):
        """빈칸이면 None, 숫자면 float, 숫자가 아니면 ValueError."""
        if text is False or text is None:
            return None
        text = str(text).strip().replace(',', '')
        if not text:
            return None
        return float(text)

    @api.depends('value_input')
    def _compute_value(self):
        for line in self:
            try:
                number = self._parse_value(line.value_input)
            except ValueError:
                number = None
            line.has_value = number is not None
            line.value = number if number is not None else 0.0

    @api.depends('item_id', 'has_value', 'value', 'lower_limit', 'upper_limit')
    def _compute_result(self):
        for line in self:
            if not line.has_value or not line.item_id:
                line.result = False
                continue
            within = (
                float_compare(line.value, line.lower_limit, precision_digits=6) >= 0
                and float_compare(line.value, line.upper_limit, precision_digits=6) <= 0
            )
            line.result = 'pass' if within else 'fail'

    @api.onchange('item_id')
    def _onchange_item_id(self):
        for line in self:
            line.lower_limit = line.item_id.lower_limit
            line.upper_limit = line.item_id.upper_limit

    @api.constrains('value_input')
    def _check_value_input(self):
        for line in self:
            try:
                self._parse_value(line.value_input)
            except ValueError:
                raise ValidationError(_("측정값 '%s'은(는) 숫자가 아닙니다.", line.value_input))

    @api.constrains('inspection_id', 'item_id')
    def _check_unique_item(self):
        for line in self:
            if self.sudo().search_count([
                ('inspection_id', '=', line.inspection_id.id),
                ('item_id', '=', line.item_id.id),
                ('id', '!=', line.id),
            ], limit=1):
                raise ValidationError(_(
                    "검사 '%(inspection)s'에 검사 항목 '%(item)s'이(가) 이미 있습니다. "
                    "한 검사에 같은 검사 항목을 두 번 넣을 수 없습니다.",
                    inspection=line.inspection_id.name, item=line.item_id.name))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def _check_inspection_editable(self, inspections):
        if is_internal(self):
            return
        if inspections.filtered(lambda r: r.state != 'draft'):
            raise UserError(_("완료된 검사의 측정값과 판정은 바꿀 수 없습니다."))
        inspections._check_owner_or_manager(_("고칠"))

    def _check_item_active(self, item_id):
        item = self.env['mes.qc.item'].with_context(active_test=False).browse(item_id).exists()
        if item and not item.active:
            raise ValidationError(_(
                "사용 중지된 검사 항목 '%s'은(는) 측정 줄에 고를 수 없습니다.", item.name))

    @api.model_create_multi
    def create(self, vals_list):
        internal = is_internal(self)
        Item = self.env['mes.qc.item'].with_context(active_test=False)
        inspections = self.env['mes.qc.inspection']
        for vals in vals_list:
            if not internal:
                for fname in self._PROTECTED_FIELDS:
                    vals.pop(fname, None)
            if vals.get('item_id'):
                self._check_item_active(vals['item_id'])
                item = Item.browse(vals['item_id'])
                vals['lower_limit'] = item.lower_limit
                vals['upper_limit'] = item.upper_limit
            if vals.get('inspection_id'):
                inspections |= inspections.browse(vals['inspection_id'])
        self._check_inspection_editable(inspections)
        return super().create(vals_list)

    def write(self, vals):
        if not is_internal(self):
            if self._PROTECTED_FIELDS.intersection(vals):
                raise UserError(_("기준값과 판정은 직접 바꿀 수 없습니다."))
            self._check_inspection_editable(self.inspection_id)
            if vals.get('inspection_id'):
                self._check_inspection_editable(
                    self.env['mes.qc.inspection'].browse(vals['inspection_id']))
            if vals.get('item_id'):
                self._check_item_active(vals['item_id'])
                item = self.env['mes.qc.item'].with_context(active_test=False).browse(vals['item_id'])
                vals = dict(vals, lower_limit=item.lower_limit, upper_limit=item.upper_limit)
                return super(MesQcInspectionLine, internal_env(self)).write(vals)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_only_draft(self):
        self._check_inspection_editable(self.inspection_id)
