from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.db import DatabaseError
from django.test import Client, RequestFactory, TestCase
from django.utils import timezone

from .models import Customer, Orders, SupportTicket
from .views import SupportView


class SupportResponseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('support_staff', is_staff=True)
        cls.other_staff = User.objects.create_user('support_staff_2', is_staff=True)
        cls.inactive = User.objects.create_user('inactive_staff', is_staff=True, is_active=False)
        cls.owner_user = User.objects.create_user('owner')
        cls.other_user = User.objects.create_user('other_owner')
        cls.owner = Customer.objects.create(Cid='S0001', Cname='Owner', Caddress='A', Chouseholdsize=1, Cmealsperweek=0, Cuser=cls.owner_user)
        cls.other = Customer.objects.create(Cid='S0002', Cname='Other', Caddress='B', Chouseholdsize=1, Cmealsperweek=0, Cuser=cls.other_user)
        cls.order = Orders.objects.create(Oid='S00001', Ocustomer=cls.owner, Odate=timezone.localdate(), Oaddress='Recorded address')
        cls.other_order = Orders.objects.create(Oid='S00002', Ocustomer=cls.other, Odate=timezone.localdate(), Oaddress='Other address')
        cls.ticket = SupportTicket.objects.create(Torder=cls.order, Tsubject='Missing item', Tmessage='<script>customer message</script>')
        cls.newer = SupportTicket.objects.create(Torder=cls.other_order, Tsubject='New issue', Tmessage='Help')
        cls.answered = SupportTicket.objects.create(Torder=cls.order, Tsubject='Old answer', Tmessage='Question', Tstatus='answered', Tresponse='Earlier', Tresponder=cls.staff, Tresponded=timezone.now())
        SupportTicket.objects.filter(pk=cls.ticket.pk).update(Tsubmitted=timezone.now() - timedelta(days=2))
        SupportTicket.objects.filter(pk=cls.newer.pk).update(Tsubmitted=timezone.now() - timedelta(days=1))
        SupportTicket.objects.filter(pk=cls.answered.pk).update(Tsubmitted=timezone.now() - timedelta(days=3))

    def setUp(self):
        self.client.force_login(self.staff)
        self.path = f'/adminpanel/support/{self.ticket.pk}'

    def customer_client(self, customer):
        client = Client()
        client.force_login(customer.Cuser)
        session = client.session
        session['Cid'] = customer.pk
        session.save()
        return client

    def test_list_order_detail_empty_and_get_immutable(self):
        before = list(SupportTicket.objects.order_by('pk').values())
        response = self.client.get('/adminpanel/support')
        self.assertEqual([t.pk for t in response.context['tickets']], [self.ticket.pk, self.newer.pk, self.answered.pk])
        response = self.client.get(self.path)
        for text in ['Missing item', 'S00001', 'Owner', '&lt;script&gt;customer message&lt;/script&gt;']:
            self.assertContains(response, text)
        self.assertNotContains(response, '<script>customer message</script>')
        self.assertEqual(before, list(SupportTicket.objects.order_by('pk').values()))
        SupportTicket.objects.all().delete()
        self.assertContains(self.client.get('/adminpanel/support'), 'No tickets found.')

    def test_answer_repeat_competing_and_owner_visibility(self):
        response = self.client.post(self.path, {'Tresponse': '  <b>Resolved</b>  ', 'Tstatus': 'open', 'Tresponder': self.other_staff.pk})
        self.assertRedirects(response, self.path)
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.Tresponse, self.ticket.Tstatus, self.ticket.Tresponder_id), ('<b>Resolved</b>', 'answered', self.staff.pk))
        timestamp = self.ticket.Tresponded
        self.assertIsNotNone(timestamp)
        self.assertContains(self.client.get(self.path), '&lt;b&gt;Resolved&lt;/b&gt;')
        self.client.force_login(self.other_staff)
        self.assertContains(self.client.post(self.path, {'Tresponse': 'Replacement'}), 'already been answered')
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.Tresponse, self.ticket.Tresponder_id, self.ticket.Tresponded), ('<b>Resolved</b>', self.staff.pk, timestamp))
        owner = self.customer_client(self.owner)
        page = owner.get('/store/orders/S00001')
        self.assertContains(page, '&lt;b&gt;Resolved&lt;/b&gt;')
        self.assertNotContains(page, '<b>Resolved</b>')
        other = self.customer_client(self.other)
        page = other.get('/store/orders/S00001')
        self.assertNotContains(page, 'Resolved')
        self.assertNotContains(page, 'Missing item')
        other.post('/store/orders/S00001', {'Tsubject': 'attack', 'Tmessage': 'attack'})
        self.assertFalse(SupportTicket.objects.filter(Tsubject='attack').exists())

    def test_validation_retains_input_and_boundary(self):
        for value, error in [('', 'Please enter a response.'), ('  \n  ', 'Please enter a response.'), ('z' * 2001, 'at most 2000')]:
            with self.subTest(length=len(value)):
                response = self.client.post(self.path, {'Tresponse': value})
                self.assertContains(response, error)
                self.assertEqual(response.wsgi_request.POST['Tresponse'], value)
                self.ticket.refresh_from_db()
                self.assertEqual(self.ticket.Tstatus, 'open')
        self.assertEqual(self.client.post(self.path, {'Tresponse': 'z' * 2000}).status_code, 302)

    def test_database_failure_retains_response_and_record(self):
        with patch('django.db.models.query.QuerySet.update', side_effect=DatabaseError('unavailable')):
            response = self.client.post(self.path, {'Tresponse': 'Keep this draft'})
        self.assertContains(response, 'could not be saved')
        self.assertContains(response, 'Keep this draft')
        self.ticket.refresh_from_db()
        self.assertEqual((self.ticket.Tstatus, self.ticket.Tresponse, self.ticket.Tresponder, self.ticket.Tresponded), ('open', '', None, None))

    def test_unknown_methods_permissions_revocation_and_csrf(self):
        self.assertEqual(self.client.get('/adminpanel/support/999999').status_code, 404)
        self.assertEqual(self.client.post('/adminpanel/support/999999', {'Tresponse': 'x'}).status_code, 404)
        self.assertEqual(self.client.post('/adminpanel/support', {'Tresponse': 'x'}).status_code, 405)
        self.assertEqual(self.client.put(self.path).status_code, 405)
        for user in [None, self.owner_user, self.inactive]:
            client = Client()
            if user:
                client.force_login(user)
            self.assertEqual(client.get(self.path).status_code, 302)
            self.assertEqual(client.post(self.path, {'Tresponse': 'x'}).status_code, 302)
            request = RequestFactory().post(self.path, {'Tresponse': 'x'})
            request.user = user or AnonymousUser()
            self.assertEqual(SupportView.as_view()(request, pk=self.ticket.pk).status_code, 302)
        self.staff.is_staff = False
        self.staff.save(update_fields=['is_staff'])
        self.assertEqual(self.client.post(self.path, {'Tresponse': 'x'}).status_code, 302)
        self.staff.is_staff = True
        self.staff.save(update_fields=['is_staff'])
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        client.get(self.path)
        self.assertEqual(client.post(self.path, {'Tresponse': 'x'}).status_code, 403)
        self.assertEqual(client.post(self.path, {'Tresponse': 'x', 'csrfmiddlewaretoken': 'invalid'}).status_code, 403)
        token = client.cookies['csrftoken'].value
        self.assertEqual(client.post(self.path, {'Tresponse': 'x', 'csrfmiddlewaretoken': token}).status_code, 302)

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.test import TransactionTestCase


class SupportResponseConcurrencyTests(TransactionTestCase):
    def test_two_clients_compete_without_overwriting(self):
        staff_a = User.objects.create_user('race_a', is_staff=True)
        staff_b = User.objects.create_user('race_b', is_staff=True)
        owner = User.objects.create_user('race_owner')
        customer = Customer.objects.create(Cid='SRACE', Cname='Race', Caddress='A', Chouseholdsize=1, Cmealsperweek=0, Cuser=owner)
        order = Orders.objects.create(Oid='SRACE1', Ocustomer=customer, Odate=timezone.localdate(), Oaddress='A')
        ticket = SupportTicket.objects.create(Torder=order, Tsubject='Issue', Tmessage='Message')
        clients = [Client(), Client()]
        clients[0].force_login(staff_a)
        clients[1].force_login(staff_b)
        barrier = Barrier(2)

        def submit(index):
            close_old_connections()
            barrier.wait(timeout=10)
            try:
                return clients[index].post(f'/adminpanel/support/{ticket.pk}', {'Tresponse': f'Answer {index}'}).status_code
            except DatabaseError:
                return 'locked'
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, range(2)))
        ticket.refresh_from_db()
        if ticket.Tstatus == 'open':
            self.assertIn('locked', outcomes)
            clients[0].post(f'/adminpanel/support/{ticket.pk}', {'Tresponse': 'Retry answer'})
            ticket.refresh_from_db()
        self.assertEqual(ticket.Tstatus, 'answered')
        self.assertIn(ticket.Tresponse, ['Answer 0', 'Answer 1', 'Retry answer'])
        first = (ticket.Tresponse, ticket.Tresponder_id, ticket.Tresponded)
        clients[1].post(f'/adminpanel/support/{ticket.pk}', {'Tresponse': 'Overwrite attempt'})
        ticket.refresh_from_db()
        self.assertEqual((ticket.Tresponse, ticket.Tresponder_id, ticket.Tresponded), first)
