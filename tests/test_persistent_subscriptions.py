"""Offline subscription lifecycle tests; no QQ credentials required."""
import importlib.util
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
from typing import Callable
import unittest
from unittest.mock import patch

stub = ModuleType('listener')
stub.ChargeListener = SimpleNamespace(HOOK_CALLBACK_TYPE=Callable)
spec = importlib.util.spec_from_file_location('persistent_subscription_bot', Path(__file__).parents[1]/'bot.py')
bot = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'listener':stub, spec.name:bot}):
    spec.loader.exec_module(bot)


class Listener:
    stations = {'测试站':1}
    def register_hook(self, station, hook): self.hook = hook
    def unregister_hook(self, station, hook): self.removed = True


def make_robot(threshold=1):
    robot = bot.ChargeRobot.__new__(bot.ChargeRobot)
    robot.listener = Listener()
    async def location(station_id, free_count):
        return '空闲位置：测试替身'
    robot._get_free_location_text = location
    robot.user_data = {}
    messages = []
    robot.send_message = lambda user, message: messages.append(message)
    subscription = bot.ChargeRobot.SubscriberData(station_name='测试站', created_at=time.time(),
        expire_in_minutes=60, threshold=threshold)
    robot.add_subscriber(123, subscription, echo=False)
    return robot, subscription, messages


class PersistentSubscriptionsTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_full_periods_do_not_cancel_or_spam(self):
        robot, subscription, messages = make_robot()
        for count in (0, 1, 0, 0, 1, 0, 0, 1):
            self.assertFalse(await subscription.hook({'freePileCount':count}))
            self.assertIn('测试站', robot.user_data[123])
        self.assertEqual(len(messages), 5)
        self.assertEqual(sum('继续监测' in text for text in messages), 2)
        self.assertEqual(sum('已有足够' in text for text in messages), 3)

    async def test_threshold_is_respected_after_full(self):
        robot, subscription, messages = make_robot(threshold=2)
        for count in (2, 0, 1):
            self.assertFalse(await subscription.hook({'freePileCount':count}))
        self.assertEqual(len(messages), 2)
        self.assertFalse(await subscription.hook({'freePileCount':2}))
        self.assertEqual(len(messages), 3)

    async def test_initial_availability_notifies(self):
        robot, subscription, messages = make_robot()
        self.assertFalse(await subscription.hook({'freePileCount':1}))
        self.assertEqual(len(messages), 1)

    async def test_expired_subscription_ends_before_availability_alert(self):
        robot, subscription, messages = make_robot()
        with patch.object(bot.time, 'time', return_value=subscription.created_at+3600):
            self.assertTrue(await subscription.hook({'freePileCount':1}))
        self.assertEqual(len(messages), 1)
        self.assertIn('到期', messages[0])
        self.assertFalse(robot.user_data)
        self.assertTrue(robot.listener.removed)

    async def test_manual_cancel_still_works(self):
        robot, subscription, messages = make_robot()
        robot.remove_subscriber(123, '测试站')
        self.assertFalse(robot.user_data)
        self.assertTrue(robot.listener.removed)


if __name__ == '__main__':
    unittest.main()
