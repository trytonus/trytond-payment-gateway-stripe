# -*- coding: utf-8 -*-
"""
    tests/conftest.py

    :copyright: (C) 2015 by Fulfil.IO Inc.
    :license: see LICENSE for more details.
"""
import os
import time
import datetime
from collections import namedtuple
from trytond.config import config
from trytond.pool import Pool
from dateutil.relativedelta import relativedelta
import pytest


def pytest_addoption(parser):

    parser.addoption(
        "--db", action="store", default="sqlite",
        help="Run on database: sqlite or postgres"
        )
    parser.addoption(
        "--reuse-db", action="store_true", default=False,
        help="Reuse the previously created database"
        )
    parser.addoption(
        "--reset-db", action="store_true", default=False,
        help="Clear local database and initialise"
        )


@pytest.fixture(scope='session', autouse=True)
def install_module(request):
    """Install tryton module in specified database.
     """
    reuse_db = request.config.getoption("--reuse-db")

    if request.config.getoption("--db") == 'sqlite':
        os.environ['TRYTOND_DATABASE_URI'] = "sqlite://"
        if reuse_db:
            # A hack to check if the database exists and if it
            # does, load that and run tests.
            Database = backend.get('Database')

            # cursor.test forgets to set flavor!
            # no time to report a bug!
            Flavor.set(Database.flavor)
            os.environ['DB_NAME'] = 'fulfilio'
        else:
            os.environ['DB_NAME'] = ':memory:'

    elif request.config.getoption("--db") == 'postgres':
        os.environ['TRYTOND_DATABASE_URI'] = "postgresql://"
        if reuse_db:
            os.environ['DB_NAME'] = 'test_fulfilio'
        else:
            os.environ['DB_NAME'] = 'test_' + str(int(time.time()))

    if reuse_db:
        Database = backend.get('Database')
        database = Database().connect()
        cursor = database.cursor()
        databases = database.list(cursor)
        cursor.close()
        if os.environ['DB_NAME'] in databases:
            if request.config.getoption("--reset-db"):
                    cursor = database.cursor()
                    databases = database.drop(cursor, os.environ['DB_NAME'])
                    cursor.close()
            else:
                # tryton test forgets to init the pool
                # for existing database
                Pool(os.environ['DB_NAME']).init()

    config.set('database', 'uri', os.environ['TRYTOND_DATABASE_URI'])
    from trytond.tests import test_tryton
    test_tryton.install_module('payment_gateway_stripe')


@pytest.yield_fixture()
def transaction(request):
    """Yields transaction with installed module.
    """

    # Importing transaction directly causes cyclic dependency in 3.6
    from trytond.tests.test_tryton import USER, CONTEXT, DB_NAME, POOL
    from trytond.tools.singleton import Singleton  # noqa
    from trytond.transaction import Transaction
    from trytond.cache import Cache

    # Inject helper functions in instance on which test function was collected.
    request.instance.POOL = POOL
    request.instance.USER = USER
    request.instance.CONTEXT = CONTEXT
    request.instance.DB_NAME = DB_NAME

    transaction = Transaction()

    with transaction.start(DB_NAME, USER, context=CONTEXT) as txn:
        yield txn
        transaction.rollback()
        Cache.drop(DB_NAME)


@pytest.fixture(scope='session')
def dataset(request):
    """Create minimal data needed for testing
    """
    from trytond.transaction import Transaction
    from trytond.tests.test_tryton import USER, CONTEXT, DB_NAME, POOL

    Party = POOL.get('party.party')
    Company = POOL.get('company.company')
    Country = POOL.get('country.country')
    Subdivision = POOL.get('country.subdivision')
    Employee = POOL.get('company.employee')
    Currency = POOL.get('currency.currency')
    User = POOL.get('res.user')
    FiscalYear = POOL.get('account.fiscalyear')
    Sequence = POOL.get('ir.sequence')
    AccountTemplate = POOL.get('account.account.template')
    Account = POOL.get('account.account')
    Journal = POOL.get('account.journal')
    PaymentGateway = POOL.get('payment_gateway.gateway')
    AccountCreateChart = POOL.get('account.create_chart', type="wizard")

    with Transaction().start(DB_NAME, USER, context=CONTEXT) as transaction:
        # Create company, employee and set it user's current company
        usd, = Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])

        country_us, = Country.create([{
            'name': 'United States',
            'code': 'US',
        }])
        subdivision_florida, = Subdivision.create([{
            'name': 'Florida',
            'code': 'US-FL',
            'country': country_us.id,
            'type': 'state'
        }])
        subdivision_california, = Subdivision.create([{
            'name': 'California',
            'code': 'US-CA',
            'country': country_us.id,
            'type': 'state'
        }])

        company_party, = Party.create([{
            'name': 'ABC Corp.',
            'addresses': [('create', [{
                'name': 'ABC Corp.',
                'street': '247 High Street',
                'zip': '94301-1041',
                'city': 'Palo Alto',
                'country': country_us.id,
                'subdivision': subdivision_california.id,
            }])],
            'contact_mechanisms': [('create', [{
                'type': 'phone',
                'value': '123456789'
            }])]
        }])

        employee_party, = Party.create([{
            'name': 'Prakash Pandey',
        }])
        company, = Company.create([{
            'party': company_party.id,
            'currency': usd.id,
        }])
        employee, = Employee.create([{
            'party': employee_party.id,
            'company': company.id,
        }])
        User.write(
            [User(USER)], {
                'main_company': company.id,
                'company': company.id,
            }
        )
        CONTEXT.update(User.get_preferences(context_only=True))

        # Create fiscal year
        date = datetime.date.today()

        post_move_sequence, = Sequence.create([{
            'name': '%s' % date.year,
            'code': 'account.move',
            'company': company.id,
        }])

        fiscal_year, = FiscalYear.create([{
            'name': '%s' % date.year,
            'start_date': date + relativedelta(month=1, day=1),
            'end_date': date + relativedelta(month=12, day=31),
            'company': company.id,
            'post_move_sequence': post_move_sequence.id,
        }])
        FiscalYear.create_period([fiscal_year])

        # Create minimal chart of account
        account_template, = AccountTemplate.search([
            ('parent', '=', None),
            ('name', '=', 'Minimal Account Chart')
        ])

        session_id, _, _ = AccountCreateChart.create()
        create_chart = AccountCreateChart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company.id),
        ])
        payable, = Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company.id),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

        account_revenue, = Account.search([
            ('kind', '=', 'revenue')
        ])
        account_expense, = Account.search([
            ('kind', '=', 'expense')
        ])

        # Create customer
        customer, = Party.create([{
            'name': 'John Doe',
            'addresses': [('create', [{
                'name': 'John Doe',
                'street': '250 NE 25th St',
                'zip': '33137',
                'city': 'Miami, Miami-Dade',
                'country': country_us.id,
                'subdivision': subdivision_florida.id,
            }])],
            'contact_mechanisms': [('create', [{
                'type': 'phone',
                'value': '123456789'
            }])]
        }])

        cash_journal, = Journal.search(
            [('type', '=', 'cash')], limit=1
        )
        Journal.write([cash_journal], {
            'debit_account': account_expense.id
        })

        stripe_gateway = PaymentGateway(
            name='Credit Card - Stripe',
            journal=cash_journal,
            provider='stripe',
            method='credit_card',
            stripe_api_key="sk_test_Xw6QdFU31e8mcmcdeMt7DoiE",
            test=True
        )
        stripe_gateway.save()

        result = {
            'customer': customer,
            'company': company,
            'stripe_gateway': stripe_gateway,
        }

        transaction.commit()

    def get():
        from trytond.model import Model

        for key, value in result.iteritems():
            if isinstance(value, Model):
                result[key] = value.__class__(value.id)
        return namedtuple('Dataset', result.keys())(**result)

    return get


