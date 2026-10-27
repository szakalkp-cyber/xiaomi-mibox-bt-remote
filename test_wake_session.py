import unittest
from types import SimpleNamespace
from wake_session import WakeSession


class Manager:
    def __init__(self):
        self.registrations = []
        self.removals = []

    def RegisterAdvertisement(self, path, options, **callbacks):
        self.registrations.append((path, callbacks))

    def UnregisterAdvertisement(self, path):
        self.removals.append(path)


class WakeLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.manager = Manager()
        self.timers = {}
        self.cancelled = []
        self.messages = []
        def schedule(seconds, callback):
            self.timers[1] = (seconds, callback)
            return 1
        self.session = WakeSession(self.manager, SimpleNamespace(path='/wake'),
                                   schedule, self.cancelled.append, self.messages.append)

    def ready(self):
        self.manager.registrations[-1][1]['reply_handler']()

    def test_wake_only_removes_its_own_advertisement(self):
        self.assertTrue(self.session.start())
        self.ready()
        seconds, finish = self.timers[1]
        self.assertEqual(seconds, 8)
        self.assertFalse(finish())
        self.assertEqual(self.manager.removals, ['/wake'])
        self.assertTrue(self.session.start())

    def test_overlapping_wakes_do_not_create_multiple_advertisements(self):
        self.session.start()
        self.assertFalse(self.session.start())
        self.ready()
        self.assertFalse(self.session.start())
        self.assertEqual(len(self.manager.registrations), 1)

    def test_registration_failure_is_retryable_without_removing_normal_advert(self):
        self.session.start()
        self.manager.registrations[0][1]['error_handler'](RuntimeError('no capacity'))
        self.assertEqual(self.manager.removals, [])
        self.assertEqual(self.timers, {})
        self.assertTrue(self.session.start())

    def test_shutdown_before_registration_reply_cleans_up_late_success(self):
        self.session.start()
        self.session.close()
        self.ready()
        self.assertEqual(self.manager.removals, ['/wake'])
        self.assertEqual(self.timers, {})
        self.assertFalse(self.session.start())

    def test_shutdown_cancels_timer_and_removes_advertisement_once(self):
        self.session.start()
        self.ready()
        self.session.close()
        self.session.close()
        self.assertEqual(self.cancelled, [1])
        self.assertEqual(self.manager.removals, ['/wake'])

    def test_unregister_failure_is_not_reported_as_success_and_close_retries(self):
        self.session.start()
        self.ready()
        remove = self.manager.UnregisterAdvertisement
        def fail(path):
            raise RuntimeError('temporary bus failure')
        self.manager.UnregisterAdvertisement = fail
        self.timers[1][1]()
        self.assertTrue(self.session.registered)
        self.assertFalse(self.session.start())
        self.assertFalse(any('zakończona' in message for message in self.messages))
        self.manager.UnregisterAdvertisement = remove
        self.session.close()
        self.assertEqual(self.manager.removals, ['/wake'])
        self.assertFalse(self.session.registered)

    def test_bluez_release_cancels_timer_without_duplicate_unregister(self):
        self.session.start()
        self.ready()
        self.session.released()
        self.session.close()
        self.assertEqual(self.cancelled, [1])
        self.assertEqual(self.manager.removals, [])


if __name__ == '__main__':
    unittest.main()
