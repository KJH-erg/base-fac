from odoo import api, fields, models


class ExampleNote(models.Model):
    _name = 'example.note'
    _description = 'Example Note'

    name = fields.Char(required=True)
    body = fields.Text()
    word_count = fields.Integer(compute='_compute_word_count', store=True)

    @api.depends('body')
    def _compute_word_count(self):
        for note in self:
            note.word_count = len((note.body or '').split())
