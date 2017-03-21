# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for details.
"""
from trytond.pool import Pool
from party import Address, PaymentProfile, Party
from transaction import PaymentGatewayStripe, PaymentTransactionStripe, \
    AddPaymentProfile


def register():
    Pool.register(
        Address,
        PaymentProfile,
        PaymentGatewayStripe,
        PaymentTransactionStripe,
        Party,
        module='payment_gateway_stripe', type_='model'
    )
    Pool.register(
        AddPaymentProfile,
        module='payment_gateway_stripe', type_='wizard'
    )
