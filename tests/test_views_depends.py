# -*- coding: utf-8 -*-
"""
    tests/test_views_depends.py

    :copyright: (C) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for more details.
"""


class TestViewDepends:

    def test_views(self):
        "Test all tryton views"

        from trytond.tests.test_tryton import test_view
        test_view('payment_gateway_stripe')

    def test_depends(self):
        "Test missing depends on fields"

        from trytond.tests.test_tryton import test_depends
        test_depends()
