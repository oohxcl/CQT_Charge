import asyncio
import importlib.util
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace
from typing import Callable
import unittest
from unittest.mock import AsyncMock, patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from free_locations import free_location_text

stub = ModuleType('listener')
stub.ChargeListener = SimpleNamespace(HOOK_CALLBACK_TYPE=Callable)
spec = importlib.util.spec_from_file_location('location_bot_test', HERE/'bot.py')
bot = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'listener': stub, spec.name: bot}):
    spec.loader.exec_module(bot)


def record(box, socket, status='空闲'):
    return {'boxNumber': box, 'pileNumber': socket, 'showStatusString': status}


class LocationTests(unittest.TestCase):
    def test_groups_sorted_distinct_and_excludes_busy_faults(self):
        text = free_location_text([record(2, 10), record(1, 7), record(1, 2),
            record(1, 2), record(3, 1, '充电中'), record(3, 2, '离线'), record(3, 3, '故障')], 3)
        self.assertIn('1号充电桩：2号、7号插座', text)
        self.assertIn('2号充电桩：10号插座', text)
        self.assertNotIn('3号充电桩', text)
        self.assertNotIn('状态可能', text)

    def test_missing_ids_and_count_changes_are_explicit(self):
        text = free_location_text([record(None, 2), record(1, 3), record(2, 2, '')], 4)
        self.assertIn('缺少完整编号', text)
        self.assertIn('缺少状态文字', text)
        self.assertIn('汇总显示4个空闲，详情查到2个', text)


class Listener:
    stations = {'测试站': 1}
    def __init__(self, details):
        self.client_controller = SimpleNamespace(get_station_info=AsyncMock(return_value=details))
        self.get_station_status = AsyncMock(return_value={1:{'id':1,'stationName':'测试站','freePileCount':2,'stationDeviceType':2}})
    def register_hook(self, name, hook): self.hook = hook
    def unregister_hook(self, name, hook): self.removed = True


def make_robot(details):
    robot = bot.ChargeRobot.__new__(bot.ChargeRobot)
    robot.listener = Listener(details)
    robot.user_data = {}
    messages = []
    robot.send_message = lambda user, message: messages.append(message)
    subscription = bot.ChargeRobot.SubscriberData(station_name='测试站', created_at=time.time(), expire_in_minutes=60, threshold=1)
    robot.add_subscriber(123, subscription, echo=False)
    return robot, subscription, messages


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_alert_full_and_reopened_keep_subscription(self):
        robot, subscription, messages = make_robot([record(1, 2), record(2, 3)])
        for count in (2, 0, 0, 2):
            self.assertFalse(await subscription.hook({'freePileCount':count}))
            self.assertIn('测试站', robot.user_data[123])
        self.assertEqual(len(messages), 3)
        self.assertIn('1号充电桩：2号插座', messages[0])
        self.assertIn('继续监测', messages[1])
        self.assertIn('2号充电桩：3号插座', messages[2])

    async def test_shared_requests_and_zero_no_query(self):
        robot, _, _ = make_robot([record(1, 1)])
        await asyncio.gather(*(robot._get_free_location_text(1, 1) for _ in range(5)))
        self.assertEqual(robot.listener.client_controller.get_station_info.await_count, 1)
        await robot._get_free_location_text(2, 0)
        self.assertEqual(robot.listener.client_controller.get_station_info.await_count, 1)

    async def test_detail_failure_does_not_suppress_count_alert(self):
        robot, subscription, messages = make_robot([])
        robot.listener.client_controller.get_station_info.side_effect = RuntimeError('network failure')
        self.assertFalse(await subscription.hook({'freePileCount':1}))
        self.assertIn('当前空闲充电位数量：1', messages[0])
        self.assertIn('暂时查询失败', messages[0])

    async def test_list_remains_summary_only(self):
        robot, _, messages = make_robot([record(1, 4), record(2, 8)])
        before = asyncio.all_tasks()
        robot.list_stations(123)
        tasks = asyncio.all_tasks() - before
        await asyncio.gather(*tasks)
        self.assertEqual(len(messages), 1)
        self.assertIn('(空闲 2)', messages[0])
        self.assertNotIn('空闲位置', messages[0])
        self.assertNotIn('号插座', messages[0])
        robot.listener.client_controller.get_station_info.assert_not_awaited()

    async def test_expiry_and_display_preserved(self):
        robot, subscription, messages = make_robot([])
        with patch.object(bot.time, 'time', return_value=subscription.created_at+1800):
            robot.list_subscriptions(123)
        self.assertIn('剩余：30 分钟', messages[-1])
        with patch.object(bot.time, 'time', return_value=subscription.created_at+3601):
            self.assertTrue(await subscription.hook({'freePileCount':1}))
        self.assertIn('到期', messages[-1])
        self.assertFalse(robot.user_data)


if __name__ == '__main__':
    unittest.main()
