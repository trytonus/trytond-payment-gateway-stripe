# -*- coding: utf-8 -*-
"""
    tests/test_payment_gateway.py

    :copyright: (C) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for more details.
"""
from decimal import Decimal

import stripe
import pytest
# Importing transaction directly causes cyclic dependency in 3.6
from trytond.tools.singleton import Singleton  # noqa
from trytond.transaction import Transaction
from trytond.exceptions import UserError
from trytond.config import config

config.set('database', 'path', '/tmp')

DUMMY_CARD = {
    'number': '4242424242424242',
    'exp_month': '07',
    'exp_year': '2019',
    'expiry_month': '07',
    'csc': '911',
}


class TestPaymentGateway:

    def create_payment_profile(self, party, gateway):
        """Create a payment profile for Stripe payment gateway
        """
        ProfileWizard = self.POOL.get(
            'party.party.payment_profile.add', type="wizard"
        )

        profile_wizard = ProfileWizard(ProfileWizard.create()[0])
        profile_wizard.card_info.owner = party.name
        profile_wizard.card_info.number = DUMMY_CARD['number']
        profile_wizard.card_info.expiry_month = DUMMY_CARD['expiry_month']
        profile_wizard.card_info.expiry_year = DUMMY_CARD['exp_year']
        profile_wizard.card_info.csc = DUMMY_CARD['csc']
        profile_wizard.card_info.gateway = gateway
        profile_wizard.card_info.provider = gateway.provider
        profile_wizard.card_info.address = party.addresses[0]
        profile_wizard.card_info.party = party

        with Transaction().set_context(return_profile=True):
            profile = profile_wizard.transition_add()
        return profile

    def test_add_payment_profile(self, dataset, transaction):
        """Test adding payment profile to a Party
        """
        data = dataset()

        payment_profile = self.create_payment_profile(
            data.customer, data.stripe_gateway
        )

        assert payment_profile.party.id == data.customer.id
        assert payment_profile.gateway == data.stripe_gateway
        assert payment_profile.last_4_digits == DUMMY_CARD['number'][-4:]
        assert payment_profile.expiry_month == DUMMY_CARD['expiry_month']
        assert payment_profile.expiry_year == DUMMY_CARD['exp_year']
        assert payment_profile.stripe_customer_id is not None

    def test_transaction_capture(self, dataset, transaction):
        """Test capture transaction
        """
        PaymentTransaction = self.POOL.get('payment_gateway.transaction')
        UseCardView = self.POOL.get('payment_gateway.transaction.use_card.view')

        data = dataset()

        # =========================================
        # Case I: Capture with already saved card
        # =========================================
        payment_profile = self.create_payment_profile(
            data.customer, data.stripe_gateway
        )
        transaction1, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction1.state == 'draft'

        PaymentTransaction.capture([transaction1])

        assert transaction1.state == 'posted'
        assert len(transaction1.logs) > 0

        # ====================================
        # Case II: Capture with unsaved card
        # ====================================
        transaction2, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction2.state == 'draft'

        transaction2.capture_stripe(card_info=UseCardView(
            number=DUMMY_CARD['number'],
            expiry_month=DUMMY_CARD['exp_month'],
            expiry_year=DUMMY_CARD['exp_year'],
            csc=DUMMY_CARD['csc'],
            owner=data.customer.name,
        ))

        assert transaction2.state == 'posted'
        assert len(transaction2.logs) > 0

        # ================================================
        # Case III: Transaction Failure on invalid amount
        # ================================================
        transaction3, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': -1,
        }])
        assert transaction3.state == 'draft'

        PaymentTransaction.capture([transaction3])
        assert transaction3.state == 'failed'

        # =====================================================
        # Case IV: Assert error when new customer is there with
        # no payment profile and card info
        # =====================================================
        transaction4, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction4.state == 'draft'

        with pytest.raises(UserError):
            PaymentTransaction.capture([transaction4])

    def test_transaction_auth_only(self, dataset, transaction):
        """Test transaction authorization
        """
        PaymentTransaction = self.POOL.get('payment_gateway.transaction')
        UseCardView = self.POOL.get('payment_gateway.transaction.use_card.view')

        data = dataset()

        # =========================================
        # Case I: Authorize with already saved card
        # =========================================
        payment_profile = self.create_payment_profile(
            data.customer, data.stripe_gateway
        )
        transaction1, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction1.state == 'draft'

        PaymentTransaction.authorize([transaction1])

        assert transaction1.state == 'authorized'
        assert len(transaction1.logs) > 0

        # ====================================
        # Case II: Authorize with unsaved card
        # ====================================
        transaction2, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction2.state == 'draft'

        transaction2.authorize_stripe(card_info=UseCardView(
            number=DUMMY_CARD['number'],
            expiry_month=DUMMY_CARD['exp_month'],
            expiry_year=DUMMY_CARD['exp_year'],
            csc=DUMMY_CARD['csc'],
            owner=data.customer.name,
        ))

        assert transaction2.state == 'authorized'
        assert len(transaction2.logs) > 0

        # ================================================
        # Case III: Transaction Failure on invalid amount
        # ================================================
        transaction3, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': -1,
        }])
        assert transaction3.state == 'draft'

        PaymentTransaction.authorize([transaction3])
        assert transaction3.state == 'failed'

        # =====================================================
        # Case IV: Assert error when new customer is there with
        # no payment profile and card info
        # =====================================================
        transaction4, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction4.state == 'draft'

        with pytest.raises(UserError):
            PaymentTransaction.authorize([transaction4])

    def test_transaction_auth_and_settle(self, dataset, transaction):
        """Test transaction authorization and settlement
        """
        PaymentTransaction = self.POOL.get('payment_gateway.transaction')
        UseCardView = self.POOL.get('payment_gateway.transaction.use_card.view')

        data = dataset()

        # ===================================================
        # Case I: Same or less amount than authorized amount
        # ===================================================
        payment_profile = self.create_payment_profile(
            data.customer, data.stripe_gateway
        )
        transaction1, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction1.state == 'draft'

        PaymentTransaction.authorize([transaction1])

        assert transaction1.state == 'authorized'
        assert len(transaction1.logs) > 0

        PaymentTransaction.settle([transaction1])
        assert transaction1.state == 'posted'

        # ============================================
        # Case II:  More amount than authorized amount
        # ============================================
        transaction2, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
        }])
        assert transaction2.state == 'draft'

        transaction2.authorize_stripe(card_info=UseCardView(
            number=DUMMY_CARD['number'],
            expiry_month=DUMMY_CARD['exp_month'],
            expiry_year=DUMMY_CARD['exp_year'],
            csc=DUMMY_CARD['csc'],
            owner=data.customer.name,
        ))

        assert transaction2.state == 'authorized'
        assert len(transaction2.logs) > 0

        PaymentTransaction.write([transaction2], {
            'amount': 500,
        })
        PaymentTransaction.settle([transaction2])
        assert transaction2.state == 'failed'

    def test_transaction_auth_and_cancel(self, dataset, transaction):
        """Test transaction authorization and cancellation
        """
        PaymentTransaction = self.POOL.get('payment_gateway.transaction')

        data = dataset()

        payment_profile = self.create_payment_profile(
            data.customer, data.stripe_gateway
        )
        transaction1, = PaymentTransaction.create([{
            'party': data.customer.id,
            'credit_account': data.customer.account_receivable.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': 100,
            'state': 'in-progress',
        }])

        # Assert User error if cancel request is sent
        # in state other than authorized
        with pytest.raises(UserError):
            PaymentTransaction.cancel([transaction1])

        transaction1.state = 'draft'
        transaction1.save()

        PaymentTransaction.authorize([transaction1])

        assert transaction1.state == 'authorized'
        assert len(transaction1.logs) > 0

        PaymentTransaction.cancel([transaction1])
        assert transaction1.state == 'cancel'

    def test_0080_test_transaction_refund(self, dataset, transaction):
        """Test refund transaction
        """
        PaymentTransaction = self.POOL.get('payment_gateway.transaction')

        data = dataset()

        assert data.customer.payable == Decimal('0')
        assert data.customer.receivable == Decimal('0')

        payment_profile = self.create_payment_profile(
            data.customer, data.stripe_gateway
        )
        transaction1, = PaymentTransaction.create([{
            'party': data.customer.id,
            'address': data.customer.addresses[0].id,
            'payment_profile': payment_profile.id,
            'gateway': data.stripe_gateway.id,
            'amount': Decimal('10.10'),
            'credit_account': data.customer.account_receivable.id,
        }])

        # Capture transaction
        PaymentTransaction.capture([transaction1])
        assert transaction1.state == 'posted'

        assert data.customer.payable == Decimal('0')
        assert data.customer.receivable == -Decimal('10.1')

        refund_transaction = transaction1.create_refund()

        # Refund this transaction
        PaymentTransaction.refund([refund_transaction])

        assert refund_transaction.state == 'posted'
        assert data.customer.payable == Decimal('0')
        assert data.customer.receivable == Decimal('0')

    def test_create_stripe_profile(self, dataset, transaction):
        """
        Test 'create_stripe_profile' method which should create
        a payment profile and return its id
        """
        PaymentProfile = self.POOL.get('party.payment_profile')
        data = dataset()

        stripe.api_key = data.stripe_gateway.stripe_api_key
        token = stripe.Token.create(card={
            "number": '4242424242424242',
            "exp_month": 9,
            "exp_year": 2020,
            "cvc": '123'
        })

        payment_profile_id = PaymentProfile.create_profile_using_stripe_token(
            data.customer.id, data.stripe_gateway.id, token
        )
        payment_profile = PaymentProfile(payment_profile_id)

        assert isinstance(payment_profile_id, int)
        assert payment_profile.party.id == data.customer.id
        assert payment_profile.gateway == data.stripe_gateway
        assert payment_profile.last_4_digits == '4242'
        assert payment_profile.expiry_month == '09'
        assert payment_profile.expiry_year == '2020'
        assert payment_profile.stripe_customer_id is not None


    def test_update_stripe_profile(self, dataset, transaction):
        """
        Update the card holder name and billing address
        """
        PaymentProfile = self.POOL.get('party.payment_profile')
        data = dataset()

        stripe.api_key = data.stripe_gateway.stripe_api_key
        token = stripe.Token.create(card={
            "number": '4242424242424242',
            "exp_month": 9,
            "exp_year": 2020,
            "cvc": '123'
        })

        payment_profile_id = PaymentProfile.create_profile_using_stripe_token(
            data.customer.id, data.stripe_gateway.id, token
        )
        payment_profile = PaymentProfile(payment_profile_id)

        assert isinstance(payment_profile_id, int)
        card = stripe.Customer.retrieve(
            payment_profile.stripe_customer_id
        ).sources.retrieve(payment_profile.provider_reference)

        assert card.address_line1 is None
        assert card.address_line2 is None
        assert card.address_city is None
        assert card.address_zip is None
        assert card.address_state is None
        assert card.address_country is None

        # Now update the address on fulfil
        payment_profile.update_stripe()

        # read card again
        card = stripe.Customer.retrieve(
            payment_profile.stripe_customer_id
        ).sources.retrieve(payment_profile.provider_reference)
        assert card.address_line1 == payment_profile.address.street
        assert card.address_line2 == payment_profile.address.streetbis
        assert card.address_city == payment_profile.address.city
        assert card.address_zip == payment_profile.address.zip
        assert card.address_state == payment_profile.address.subdivision.code
        assert card.address_country == payment_profile.address.country.code