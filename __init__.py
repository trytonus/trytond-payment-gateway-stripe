# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for details.
"""
from trytond.pool import Pool


def register():
    Pool.register(
        module='payment_gateway_stripe', type_='model'
    )
