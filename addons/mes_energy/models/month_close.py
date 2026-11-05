import re

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MONTH_RE = re.compile(r'^\d{4}-(0[1-9]|1[0-2])$')


class MesEnergyMonthClose(models.Model):
    _name = 'mes.energy.month.close'
    _description = '에너지 월 마감'
    _order = 'name desc'

    name = fields.Char(string='연월', required=True, readonly=True, help='YYYY-MM 형식')
    closed_at = fields.Datetime(string='마감 일시', readonly=True, default=fields.Datetime.now)
    closed_by = fields.Many2one('res.users', string='마감한 사람', readonly=True,
                                default=lambda self: self.env.user)

    _name_uniq = models.Constraint(
        'unique(name)',
        '이미 마감된 달입니다.',
    )

    @api.constrains('name')
    def _check_name_format(self):
        for close in self:
            if not MONTH_RE.match(close.name or ''):
                raise ValidationError('연월은 YYYY-MM 형식이어야 합니다.')

    def _check_manager(self):
        if not self.env.su and not self.env.user.has_group('mes_energy.group_energy_manager'):
            raise AccessError('월 마감과 마감 취소는 에너지 관리자만 할 수 있습니다.')

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager()
        Usage = self.env['mes.energy.usage'].sudo()
        seen = set()
        for vals in vals_list:
            name = (vals.get('name') or '').strip()
            if not MONTH_RE.match(name):
                raise ValidationError('연월은 YYYY-MM 형식이어야 합니다.')
            if name in seen or self.sudo().search_count([('name', '=', name)], limit=1):
                raise UserError('%s은(는) 이미 마감된 달입니다.' % name)
            seen.add(name)
            missing = Usage.search_count([('month', '=', name), ('is_missing', '=', True)])
            if missing:
                raise UserError(
                    '%s에 누락 기록(전력·용수 중 하나라도 비어 있는 기록)이 %d건 남아 있어 마감할 수 없습니다.'
                    % (name, missing))
            vals['name'] = name
            vals['closed_at'] = fields.Datetime.now()
            vals['closed_by'] = self.env.uid
        return super().create(vals_list)

    def write(self, vals):
        if 'name' in vals:
            raise UserError('마감한 연월은 바꿀 수 없습니다. 마감 취소 후 다시 마감하세요.')
        self._check_manager()
        return super().write(vals)

    def unlink(self):
        self._check_manager()
        return super().unlink()

    def action_cancel_close(self):
        """마감 취소: 월 마감 기록을 지운다."""
        self._check_manager()
        self.unlink()
        return self.env['ir.actions.act_window']._for_xml_id('mes_energy.action_mes_energy_month_close')
