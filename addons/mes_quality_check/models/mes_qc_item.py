from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .mes_qc_common import internal_env


class MesQcItem(models.Model):
    _name = 'mes.qc.item'
    _description = '검사 항목'
    _order = 'name, id'

    name = fields.Char(string='항목 이름', required=True)
    uom = fields.Char(string='단위')
    lower_limit = fields.Float(string='하한값', required=True, digits=(16, 4))
    upper_limit = fields.Float(string='상한값', required=True, digits=(16, 4))
    active = fields.Boolean(string='사용', default=True)
    line_count = fields.Integer(string='사용된 측정 줄 수', compute='_compute_line_count')

    def _compute_line_count(self):
        data = self.env['mes.qc.inspection.line']._read_group(
            [('item_id', 'in', self.ids)], ['item_id'], ['__count'])
        counts = {item.id: count for item, count in data}
        for item in self:
            item.line_count = counts.get(item.id, 0)

    @api.constrains('lower_limit', 'upper_limit')
    def _check_limits(self):
        for item in self:
            if item.lower_limit > item.upper_limit:
                raise ValidationError(_(
                    "검사 항목 '%(name)s'의 하한값(%(low)s)이 상한값(%(high)s)보다 클 수 없습니다.",
                    name=item.name, low=item.lower_limit, high=item.upper_limit))

    def write(self, vals):
        res = super().write(vals)
        if 'lower_limit' in vals or 'upper_limit' in vals:
            # 초안 검사의 측정 줄만 새 기준으로 다시 판정한다.
            # 완료된 검사의 측정 줄은 완료 시점의 기준과 판정을 그대로 유지한다.
            Line = internal_env(self.env['mes.qc.inspection.line'].sudo())
            for item in self:
                lines = Line.search([
                    ('item_id', '=', item.id),
                    ('inspection_id.state', '=', 'draft'),
                ])
                if lines:
                    lines.write({
                        'lower_limit': item.lower_limit,
                        'upper_limit': item.upper_limit,
                    })
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        Line = self.env['mes.qc.inspection.line'].sudo()
        for item in self:
            if Line.search_count([('item_id', '=', item.id)], limit=1):
                raise UserError(_(
                    "검사 항목 '%s'은(는) 측정 줄에 쓰였으므로 삭제할 수 없습니다. 대신 사용 중지하십시오.",
                    item.name))
