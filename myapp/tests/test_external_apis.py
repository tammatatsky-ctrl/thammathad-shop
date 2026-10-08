"""เทสต์ external API แบบไม่ต้องมี key (keyless): ThaiCalendar holidays · GeoIP · Translate.

ปรัชญาการเทสต์ไฟล์นี้: **ห้ามยิงเน็ตจริง** — mock `urllib.request.urlopen` ทุกจุด
(เว้นแต่จะเป็นการยืนยันสดที่ทำมือ) เพื่อให้ suite รันได้ offline และ deterministic.

ครอบคลุม:
- ThaiCalendar.parse_ics / holidays / is_holiday / next_business_day (ข้าม weekend + วันหยุด)
- GeoIP: private IP ต้องไม่ยิง API, normalize ข้อมูล, cache, ล่ม → None
- Translate: สำเร็จ + cache, ตรวจ "MYMEMORY WARNING" (โควตาหมด), ปฏิเสธข้อความยาวเกิน/ว่างโดยไม่ยิงเน็ต
- View: ProductTranslateView (staff only) + ETA ในหน้าสำเร็จ + คำใบ้ GeoIP ในฟอร์มที่อยู่
"""
import json
from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from myapp.models import Order
from myapp.services import GeoIP, ThaiCalendar, Translate


def _fake_response(payload: bytes):
    """object เลียนแบบ urllib response (รองรับ `with ... as resp:`) สำหรับ patch urlopen."""
    resp = mock.MagicMock()
    resp.read.return_value = payload
    resp.__enter__.return_value = resp
    return resp


class ThaiHolidayCalendarTest(TestCase):
    """ปฏิทินวันหยุดไทยจาก Google ICS (keyless) — แกะ + ใช้นับวันทำการ"""

    ICS = (
        'BEGIN:VCALENDAR\n'
        'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260101\nSUMMARY:วันขึ้นปีใหม่\nEND:VEVENT\n'
        'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260406\n'
        'SUMMARY:วันจักรี\\, รัชกาลที่ 1\nEND:VEVENT\n'
        'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260413\nSUMMARY:วันสงกรานต์\nEND:VEVENT\n'
        'END:VCALENDAR'
    )

    def test_parse_ics_maps_date_to_thai_name(self):
        parsed = ThaiCalendar.parse_ics(self.ICS)
        self.assertEqual(parsed[date(2026, 1, 1)], 'วันขึ้นปีใหม่')
        self.assertEqual(parsed[date(2026, 4, 6)], 'วันจักรี, รัชกาลที่ 1')   # unescape \,
        self.assertEqual(len(parsed), 3)

    def test_parse_ics_unfolds_continuation_lines(self):
        ics = ('BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260501\n'
               'SUMMARY:วันแรงงาน\n แห่งชาติ\nEND:VEVENT')
        self.assertEqual(ThaiCalendar.parse_ics(ics)[date(2026, 5, 1)], 'วันแรงงานแห่งชาติ')

    def test_parse_ics_ignores_broken_dates(self):
        ics = 'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20261399\nSUMMARY:วันเพี้ยน\nEND:VEVENT'
        self.assertEqual(ThaiCalendar.parse_ics(ics), {})

    @mock.patch.object(ThaiCalendar, 'holidays', return_value={date(2026, 1, 2): 'หยุดชดเชย'})
    def test_next_business_day_skips_weekend_and_holiday(self, _holidays):
        """พฤหัสฯ 1 ม.ค. 2026 → ข้าม ศ.(ชดเชย)/ส./อา. → จันทร์ 5 ม.ค. 2026"""
        eta = ThaiCalendar.next_business_day(date(2026, 1, 1))
        self.assertEqual(eta, date(2026, 1, 5))
        self.assertEqual(eta.weekday(), 0)   # จันทร์

    @mock.patch.object(ThaiCalendar, 'holidays', return_value={})
    def test_next_business_day_include_start(self, _holidays):
        """include_start=True และวันเริ่มเป็นวันทำการ → คืนวันนั้นเอง"""
        self.assertEqual(ThaiCalendar.next_business_day(date(2026, 1, 5), include_start=True),
                         date(2026, 1, 5))

    @mock.patch.object(ThaiCalendar, 'holidays', return_value={date(2026, 5, 4): 'ชดเชยวันฉัตรมงคล'})
    def test_is_holiday(self, _holidays):
        self.assertTrue(ThaiCalendar.is_holiday(date(2026, 5, 4)))
        self.assertFalse(ThaiCalendar.is_holiday(date(2026, 5, 5)))

    def test_holidays_failure_returns_empty_dict(self):
        """ICS ล่ม → {} (ไม่ raise) และแคชผลลัพธ์ไว้ (ไม่ยิงซ้ำถี่)"""
        cache.clear()
        with mock.patch('myapp.services.urllib.request.urlopen', side_effect=OSError('down')) as u:
            self.assertEqual(ThaiCalendar.holidays(2026), {})
            self.assertEqual(ThaiCalendar.holidays(2026), {})
            self.assertEqual(u.call_count, 1)
        cache.clear()

    def test_holidays_filters_non_official_observances(self):
        """ICS จริงมีวัน observance ปน (วาเลนไทน์/ตรุษจีน/คริสต์มาส) — ต้องถูกกรองออก
        เหลือเฉพาะวันหยุดราชการ เพื่อไม่ให้ ETA ข้ามวันทำการผิด"""
        ics = (
            'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260214\nSUMMARY:วันวาเลนไทน์\nEND:VEVENT\n'
            'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260217\nSUMMARY:วันตรุษจีน\nEND:VEVENT\n'
            'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20261225\nSUMMARY:วันคริสต์มาส\nEND:VEVENT\n'
            'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260406\nSUMMARY:วันจักรี\nEND:VEVENT\n'
            'BEGIN:VEVENT\nDTSTART;VALUE=DATE:20260413\nSUMMARY:วันสงกรานต์\nEND:VEVENT'
        ).encode()
        cache.clear()
        with mock.patch('myapp.services.urllib.request.urlopen',
                        return_value=_fake_response(ics)):
            days = ThaiCalendar.holidays(2026)
        self.assertEqual(set(days), {date(2026, 4, 6), date(2026, 4, 13)})
        cache.clear()


class GeoIPServiceTest(TestCase):
    """GeoIP (ipwho.is) — ระดับประเทศเท่านั้น; private IP ห้ามยิง API"""

    def setUp(self):
        GeoIP._cache.clear()

    def tearDown(self):
        GeoIP._cache.clear()

    def test_private_and_invalid_ips_never_call_api(self):
        with mock.patch('myapp.services.urllib.request.urlopen') as urlopen:
            for ip in ('127.0.0.1', '10.0.0.5', '192.168.1.10', '169.254.1.1',
                       '172.16.0.9', '172.31.255.1', '', '::1'):
                self.assertIsNone(GeoIP.lookup(ip), f'{ip} ต้องเป็น None')
            urlopen.assert_not_called()

    def test_is_private_boundaries(self):
        self.assertTrue(GeoIP.is_private('172.16.0.1'))
        self.assertFalse(GeoIP.is_private('172.15.0.1'))
        self.assertFalse(GeoIP.is_private('8.8.8.8'))

    def test_public_ip_normalizes_and_caches(self):
        payload = json.dumps({
            'success': True, 'country_code': 'us', 'country': 'United States',
            'region': 'California', 'city': 'Mountain View',
        }).encode()
        with mock.patch('myapp.services.urllib.request.urlopen',
                        return_value=_fake_response(payload)) as u:
            got = GeoIP.lookup('8.8.8.8')
            self.assertEqual(got['country_code'], 'US')      # normalize เป็นตัวใหญ่
            self.assertEqual(got['city'], 'Mountain View')
            GeoIP.lookup('8.8.8.8')                          # cache hit
            self.assertEqual(u.call_count, 1)

    def test_failure_returns_none(self):
        with mock.patch('myapp.services.urllib.request.urlopen', side_effect=OSError('boom')):
            self.assertIsNone(GeoIP.lookup('203.0.113.7'))


class TranslateServiceTest(TestCase):
    """Translate (MyMemory) — สำเร็จ/cache, ตรวจ warning โควตา, ปฏิเสธก่อนยิงเน็ต"""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_success_and_cache(self):
        payload = json.dumps({'responseData': {'translatedText': 'แป้นพิมพ์กลไก'},
                              'responseStatus': 200}).encode()
        with mock.patch('myapp.services.urllib.request.urlopen',
                        return_value=_fake_response(payload)) as u:
            self.assertEqual(Translate.text('Mechanical keyboard'), 'แป้นพิมพ์กลไก')
            self.assertEqual(Translate.text('Mechanical keyboard'), 'แป้นพิมพ์กลไก')
            self.assertEqual(u.call_count, 1)

    def test_quota_warning_returns_empty(self):
        payload = json.dumps({
            'responseData': {'translatedText': 'MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS'},
            'responseStatus': 200,
        }).encode()
        with mock.patch('myapp.services.urllib.request.urlopen', return_value=_fake_response(payload)):
            self.assertEqual(Translate.text('hello'), '')

    def test_rejects_before_network(self):
        with mock.patch('myapp.services.urllib.request.urlopen') as u:
            self.assertEqual(Translate.text(''), '')
            self.assertEqual(Translate.text('x' * (Translate.MAX_CHARS + 1)), '')
            self.assertEqual(Translate.text('เหมือนกัน', source='th', target='th'), '')
            u.assert_not_called()

    def test_failure_returns_empty(self):
        with mock.patch('myapp.services.urllib.request.urlopen', side_effect=OSError('down')):
            self.assertEqual(Translate.text('hello world'), '')


class ProductTranslateViewTest(TestCase):
    """ปุ่มแปลในฟอร์มสินค้า — staff เท่านั้น และต้อง degrade สุภาพเมื่อบริการแปลใช้ไม่ได้"""

    def setUp(self):
        self.staff = User.objects.create_user(username='teacher', password='pw', is_staff=True)
        self.url = reverse('product_translate')

    def test_anonymous_redirected_to_staff_login(self):
        r = self.client.post(self.url, {'description': 'Mechanical keyboard'})
        self.assertEqual(r.status_code, 302)
        self.assertIn('/staff/login/', r['Location'])

    @mock.patch('myapp.views.Translate.text', return_value='แป้นพิมพ์กลไก')
    def test_staff_gets_translation(self, _t):
        self.client.force_login(self.staff)
        r = self.client.post(self.url, {'description': 'Mechanical keyboard'},
                             HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['text'], 'แป้นพิมพ์กลไก')

    @mock.patch('myapp.views.Translate.text', return_value='')
    def test_service_unavailable_returns_502(self, _t):
        self.client.force_login(self.staff)
        r = self.client.post(self.url, {'description': 'x'}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 502)

    def test_empty_text_returns_400(self):
        self.client.force_login(self.staff)
        r = self.client.post(self.url, {'description': '   '}, HTTP_X_REQUESTED_WITH='fetch')
        self.assertEqual(r.status_code, 400)


class OrderSuccessEtaTest(TestCase):
    """หน้าสำเร็จการสั่งซื้อแสดง ETA วันทำการถัดไป (ThaiCalendar — keyless)"""

    def test_eta_line_present(self):
        order = Order.objects.create(
            customer_name='ลูกค้า ทดสอบ', phone='0812345678', address='กทม',
            total=Decimal('100.00'), payment_method='promptpay',
        )
        with mock.patch.object(ThaiCalendar, 'holidays', return_value={}):
            r = self.client.get(f"{reverse('order_success', args=[order.id])}?phone={order.phone}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'คาดจัดส่งภายใน')


class AddressGeoHintTest(TestCase):
    """คำใบ้ GeoIP ในฟอร์มที่อยู่ — แสดงเฉพาะเมื่อผู้ใช้อยู่นอกประเทศไทย (mock ผู้เข้าชม)"""

    def setUp(self):
        self.user = User.objects.create_user(username='customer@test.com', password='pw')
        self.client.force_login(self.user)

    @mock.patch('myapp.views.GeoIP.visitor',
                return_value={'country_code': 'US', 'country': 'United States',
                              'region': 'California', 'city': 'San Francisco'})
    def test_outside_thailand_shows_hint(self, _geo):
        r = self.client.get(reverse('address_add'))
        self.assertContains(r, 'อยู่นอกประเทศไทย')

    @mock.patch('myapp.views.GeoIP.visitor',
                return_value={'country_code': 'TH', 'country': 'Thailand',
                              'region': 'Bangkok', 'city': 'Bangkok'})
    def test_thailand_hides_hint(self, _geo):
        r = self.client.get(reverse('address_add'))
        self.assertNotContains(r, 'อยู่นอกประเทศไทย')
