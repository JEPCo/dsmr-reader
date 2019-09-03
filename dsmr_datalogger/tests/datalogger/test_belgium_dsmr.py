from unittest import mock
from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
import pytz

from dsmr_backend.tests.mixins import InterceptStdoutMixin
from dsmr_datalogger.models.reading import DsmrReading
from dsmr_datalogger.models.statistics import MeterStatistics
from dsmr_datalogger.models.settings import DataloggerSettings


class TestDatalogger(InterceptStdoutMixin, TestCase):
    """ Test Iskra meter, unknown DSMR version. """
    def setUp(self):
        datalogger_settings = DataloggerSettings.get_solo()
        datalogger_settings.dsmr_version = DataloggerSettings.DSMR_VERSION_2
        datalogger_settings.save()

    def _dsmr_dummy_data(self):
        return [
            "/FLU5\253769484_A\r\n",
            "\r\n",
            "0-0:96.1.4(50213)\r\n",
            "0-0:96.1.1(xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)\r\n",
            "0-0:1.0.0(190821210025S)\r\n",
            "1-0:1.8.1(000260.129*kWh)\r\n",
            "1-0:1.8.2(000338.681*kWh)\r\n",
            "1-0:2.8.1(000000.010*kWh)\r\n",
            "1-0:2.8.2(000000.425*kWh)\r\n",
            "0-0:96.14.0(0002)\r\n",
            "1-0:1.7.0(00.261*kW)\r\n",
            "1-0:2.7.0(00.000*kW)\r\n",
            "1-0:32.7.0(231.0*V)\r\n",
            "1-0:52.7.0(000.0*V)\r\n",
            "1-0:72.7.0(230.9*V)\r\n",
            "1-0:31.7.0(000*A)\r\n",
            "1-0:51.7.0(000*A)\r\n",
            "1-0:71.7.0(000*A)\r\n",
            "0-0:96.3.10(1)\r\n",
            "0-0:17.0.0(999.9*kW)\r\n",
            "1-0:31.4.0(999*A)\r\n",
            "0-0:96.13.0()\r\n",
            "0-1:24.1.0(003)\r\n",
            "0-1:96.1.1(xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx)\r\n",
            "0-1:24.4.0(1)\r\n",
            "0-1:24.2.3(190821210011S)(00029.553*m3)\r\n",
            "!BE13"
        ]

    @mock.patch('serial.Serial.open')
    @mock.patch('serial.Serial.readline')
    def _fake_dsmr_reading(self, serial_readline_mock, serial_open_mock):
        """ Fake & process an DSMR vX telegram reading. """
        serial_open_mock.return_value = None
        serial_readline_mock.side_effect = self._dsmr_dummy_data()

        self.assertFalse(DsmrReading.objects.exists())
        self._intercept_command_stdout('dsmr_datalogger', run_once=True)
        self.assertTrue(DsmrReading.objects.exists())

    def test_reading_creation(self):
        """ Test whether dsmr_datalogger can insert a reading. """
        self.assertFalse(DsmrReading.objects.exists())
        self._fake_dsmr_reading()
        self.assertTrue(DsmrReading.objects.exists())

    @mock.patch('django.utils.timezone.now')
    def test_reading_values(self, now_mock):
        """ Test whether dsmr_datalogger reads the correct values. """
        now_mock.return_value = timezone.make_aware(timezone.datetime(2019, 8, 21, hour=22))
        self._fake_dsmr_reading()
        self.assertTrue(DsmrReading.objects.exists())
        reading = DsmrReading.objects.get()
        self.assertEqual(
            reading.timestamp,
            datetime(2019, 8, 21, 19, 0, 25, tzinfo=pytz.UTC)
        )
        self.assertEqual(reading.electricity_delivered_1, Decimal('260.129'))
        self.assertEqual(reading.electricity_returned_1, Decimal('0.010'))
        self.assertEqual(reading.electricity_delivered_2, Decimal('338.681'))
        self.assertEqual(reading.electricity_returned_2, Decimal('0.425'))
        self.assertEqual(reading.electricity_currently_delivered, Decimal('0.261'))
        self.assertEqual(reading.electricity_currently_returned, Decimal('0'))
        self.assertEqual(
            reading.extra_device_timestamp,
            datetime(2019, 8, 21, 19, 0, 11, tzinfo=pytz.UTC)
        )
        self.assertEqual(reading.extra_device_delivered, Decimal('29.553'))

        meter_statistics = MeterStatistics.get_solo()
        self.assertIsNone(meter_statistics.dsmr_version)
        self.assertEqual(meter_statistics.electricity_tariff, 2)
        self.assertEqual(meter_statistics.power_failure_count, None)
        self.assertEqual(meter_statistics.long_power_failure_count, None)
        self.assertEqual(meter_statistics.voltage_sag_count_l1, None)
        self.assertEqual(meter_statistics.voltage_sag_count_l2, None)
        self.assertEqual(meter_statistics.voltage_sag_count_l3, None)
        self.assertEqual(meter_statistics.voltage_swell_count_l1, None)
        self.assertEqual(meter_statistics.voltage_swell_count_l2, None)
        self.assertEqual(meter_statistics.voltage_swell_count_l3, None)

    @mock.patch('dsmr_datalogger.signals.raw_telegram.send_robust')
    def test_raw_telegram_signal_sent(self, signal_mock):
        self.assertFalse(signal_mock.called)
        self._fake_dsmr_reading()
        self.assertTrue(signal_mock.called)