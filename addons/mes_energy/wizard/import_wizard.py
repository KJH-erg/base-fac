import base64
import csv
import io
import math
import re
from datetime import datetime

from odoo import fields, models
from odoo.exceptions import UserError

EXPECTED_HEADER = ['equipment_code', 'date', 'power_kwh', 'water_m3']
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
NUMBER_RE = re.compile(r'^[+-]?(\d+(\.\d*)?|\.\d+)$')


class MesEnergyImportWizard(models.TransientModel):
    _name = 'mes.energy.import.wizard'
    _description = '계측 파일 가져오기'

    file = fields.Binary(string='계측 파일(CSV)', attachment=False)
    filename = fields.Char(string='파일 이름')
    state = fields.Selection([('draft', '파일 선택'), ('done', '완료')], default='draft')
    created_count = fields.Integer(string='만든 줄', readonly=True)
    updated_count = fields.Integer(string='갱신한 줄', readonly=True)
    rejected_count = fields.Integer(string='거부한 줄', readonly=True)
    line_ids = fields.One2many('mes.energy.import.line', 'wizard_id', string='거부한 줄', readonly=True)

    def _read_file_text(self):
        data = self.file
        if not data:
            raise UserError('가져올 파일을 고르세요.')
        if hasattr(data, 'content'):
            raw = data.content
        elif isinstance(data, bytes):
            raw = base64.b64decode(data)
        else:
            raw = base64.b64decode(str(data))
        if isinstance(raw, str):
            return raw
        try:
            return raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise UserError('파일이 UTF-8 CSV가 아닙니다.')

    @staticmethod
    def _parse_number(text):
        if not NUMBER_RE.match(text):
            return None
        value = float(text)
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    def action_import(self):
        self.ensure_one()
        text = self._read_file_text()
        reader = csv.reader(io.StringIO(text, newline=''))
        try:
            header = next(reader)
        except StopIteration:
            raise UserError('파일이 비어 있습니다. 머리글은 %s 이어야 합니다.' % ','.join(EXPECTED_HEADER))
        except csv.Error as e:
            raise UserError('CSV 파일을 읽을 수 없습니다: %s' % e)
        if [h.strip() for h in header] != EXPECTED_HEADER:
            raise UserError(
                '머리글이 맞지 않아 아무 줄도 처리하지 않았습니다.\n'
                '필요한 머리글: %s\n파일의 머리글: %s' % (','.join(EXPECTED_HEADER), ','.join(header)))

        Usage = self.env['mes.energy.usage']
        Equipment = self.env['mes.energy.equipment'].with_context(active_test=False)
        today = fields.Date.context_today(self)
        equipment_cache = {}
        closed_cache = {}
        created = updated = 0
        rejects = []

        def reject(line_no, reason, row):
            rejects.append({'line_no': line_no, 'content': ','.join(row)[:200], 'reason': reason})

        while True:
            try:
                row = next(reader)
            except StopIteration:
                break
            except csv.Error as e:
                reject(reader.line_num, 'CSV 형식 오류: %s' % e, [])
                continue
            line_no = reader.line_num
            if not row or (len(row) == 1 and not row[0].strip()):
                # 완전히 빈 줄은 건너뛴다.
                continue
            if len(row) != len(EXPECTED_HEADER):
                reject(line_no, '열 개수가 %d개가 아닙니다.' % len(EXPECTED_HEADER), row)
                continue
            code, date_text, power_text, water_text = (cell.strip() for cell in row)
            if not code or not date_text or not power_text or not water_text:
                reject(line_no, '빈 칸이 있습니다.', row)
                continue

            if code not in equipment_cache:
                equipment_cache[code] = Equipment.search([('code', '=', code)], limit=1)
            equipment = equipment_cache[code]
            if not equipment:
                reject(line_no, '없는 설비 코드입니다: %s' % code, row)
                continue
            if not equipment.active:
                reject(line_no, '사용 중이 아닌 설비입니다: %s' % code, row)
                continue

            date = None
            if DATE_RE.match(date_text):
                try:
                    date = datetime.strptime(date_text, '%Y-%m-%d').date()
                except ValueError:
                    date = None
            if not date:
                reject(line_no, '날짜 형식 오류입니다(YYYY-MM-DD): %s' % date_text, row)
                continue

            power = self._parse_number(power_text)
            water = self._parse_number(water_text)
            if power is None or water is None:
                reject(line_no, '숫자 형식 오류입니다.', row)
                continue
            if power < 0 or water < 0:
                reject(line_no, '음수 사용량입니다.', row)
                continue
            if date > today:
                reject(line_no, '미래 날짜입니다: %s' % date_text, row)
                continue
            month = date.strftime('%Y-%m')
            if month not in closed_cache:
                closed_cache[month] = bool(Usage._closed_months({month}))
            if closed_cache[month]:
                reject(line_no, '마감된 달입니다: %s' % month, row)
                continue

            vals = {
                'power_kwh': power,
                'power_entered': True,
                'water_m3': water,
                'water_entered': True,
                'input_source': 'import',
            }
            existing = Usage.search([('equipment_id', '=', equipment.id), ('date', '=', date)], limit=1)
            try:
                with self.env.cr.savepoint():
                    if existing:
                        existing.write(vals)
                    else:
                        Usage.create(dict(vals, equipment_id=equipment.id, date=date))
                    self.env.flush_all()
            except UserError as e:  # ValidationError, AccessError 포함
                reject(line_no, str(e.args[0] if e.args else e), row)
                continue
            except Exception as e:  # noqa: BLE001 - DB 제약 위반 등도 그 줄만 거부한다
                reject(line_no, '기록하지 못했습니다: %s' % e, row)
                continue
            if existing:
                updated += 1
            else:
                created += 1

        self.line_ids.unlink()
        self.write({
            'state': 'done',
            'created_count': created,
            'updated_count': updated,
            'rejected_count': len(rejects),
            'line_ids': [(0, 0, r) for r in rejects],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': '계측 파일 가져오기',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


class MesEnergyImportLine(models.TransientModel):
    _name = 'mes.energy.import.line'
    _description = '계측 파일 가져오기 거부 줄'
    _order = 'line_no'

    wizard_id = fields.Many2one('mes.energy.import.wizard', required=True, ondelete='cascade')
    line_no = fields.Integer(string='줄 번호')
    content = fields.Char(string='내용')
    reason = fields.Char(string='이유')
