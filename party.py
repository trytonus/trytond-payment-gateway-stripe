# -*- coding: utf-8 -*-
"""
    party.py

    :copyright: (c) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for more details.
"""
import stripe

from trytond.pool import PoolMeta, Pool
from trytond.model import fields
from trytond.rpc import RPC
from trytond.exceptions import UserError

__metaclass__ = PoolMeta
__all__ = ['Address', 'PaymentProfile', 'Party']


class Address:
    __name__ = 'party.address'

    def get_address_for_stripe(self):
        """
        Return the address as a dictionary for stripe
        """
        return {
            'address_line1': self.street,
            'address_line2': self.streetbis,
            'address_city': self.city,
            'address_zip': self.zip,
            'address_state': self.subdivision and self.subdivision.name,
            'address_country': self.country and self.country.name,
        }


class PaymentProfile:
    __name__ = 'party.payment_profile'

    stripe_customer_id = fields.Char(
        'Stripe Customer ID', readonly=True
    )

    @classmethod
    def __setup__(cls):
        super(PaymentProfile, cls).__setup__()
        cls.__rpc__.update({
            'create_profile_using_stripe_token': RPC(
                instantiate=0, readonly=True
            ),
            'update_stripe': RPC(
                instantiate=0, readonly=False
            ),
        })

    def update_stripe(self):
        """
        Update this payment profile on the gateway (stripe)
        """
        assert self.gateway.provider == 'stripe'
        stripe.api_key = self.gateway.stripe_api_key

        try:
            card = stripe.Customer.retrieve(
                self.stripe_customer_id
            ).sources.retrieve(self.provider_reference)
        except (
            stripe.error.CardError, stripe.error.InvalidRequestError,
            stripe.error.AuthenticationError, stripe.error.APIConnectionError,
            stripe.error.StripeError
        ), exc:
            raise UserError(exc.json_body['error']['message'])

        # Update all the information
        card.name = self.name or self.party.name
        for key, value in self.address.get_address_for_stripe():
            if value:
                setattr(card, key, value)
        card.exp_month = self.expiry_month
        card.exp_year = self.expiry_year

        try:
            card.save()
        except (
            stripe.error.CardError, stripe.error.InvalidRequestError,
            stripe.error.AuthenticationError, stripe.error.APIConnectionError,
            stripe.error.StripeError
        ), exc:
            raise UserError(exc.json_body['error']['message'])

    @classmethod
    def create_profile_using_stripe_token(
        cls, user_id, gateway_id, token, address_id=None
    ):
        """
        Create a Payment Profile using token
        """
        Party = Pool().get('party.party')
        PaymentGateway = Pool().get('payment_gateway.gateway')
        PaymentProfile = Pool().get('party.payment_profile')

        party = Party(user_id)
        gateway = PaymentGateway(gateway_id)
        assert gateway.provider == 'stripe'
        stripe.api_key = gateway.stripe_api_key

        try:
            customer = stripe.Customer.create(
                source=token,
                description=party.name,
            )
            card = customer.sources.data[0]
        except (
            stripe.error.CardError, stripe.error.InvalidRequestError,
            stripe.error.AuthenticationError, stripe.error.APIConnectionError,
            stripe.error.StripeError
        ), exc:
            raise UserError(exc.json_body['error']['message'])
        else:
            profile, = PaymentProfile.create([{
                'name': card.name,
                'party': party.id,
                'address': address_id or party.addresses[0].id,
                'gateway': gateway.id,
                'last_4_digits': card.last4,
                'expiry_month': unicode('%02d' % card.exp_month),
                'expiry_year': unicode(card.exp_year),
                'provider_reference': card.id,
                'stripe_customer_id': customer.id,
            }])

            return profile.id


class Party:
    __name__ = 'party.party'

    def _get_stripe_customer_id(self, gateway):
        """
        Extracts and returns customer id from party's payment profile
        Return None if no customer id is found.
        :param gateway: Payment gateway to which the customer id is associated
        """
        PaymentProfile = Pool().get('party.payment_profile')

        payment_profiles = PaymentProfile.search([
            ('party', '=', self.id),
            ('stripe_customer_id', '!=', None),
            ('gateway', '=', gateway.id),
        ])
        if payment_profiles:
            return payment_profiles[0].stripe_customer_id
        return None
