from odoo.tests import TransactionCase


class TestExampleNote(TransactionCase):
    def test_word_count_follows_body(self):
        note = self.env['example.note'].create({'name': 'n', 'body': 'one two three'})
        self.assertEqual(note.word_count, 3)
        note.body = False
        self.assertEqual(note.word_count, 0)
