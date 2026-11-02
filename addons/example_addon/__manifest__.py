{
    'name': 'Example Addon',
    'version': '20.0.1.0.0',
    'summary': 'Minimal reference addon: copy it or delete it',
    'category': 'Tools',
    'author': 'Your Name',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.access.csv',
        'views/example_note_views.xml',
    ],
    'application': True,
}
