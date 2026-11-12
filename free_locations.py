"""Format documented display fields without guessing numeric status codes."""


def free_location_text(piles, expected_count):
    if not isinstance(piles, list):
        raise ValueError('Invalid device detail response')
    locations = set()
    missing = 0
    unknown = 0
    for pile in piles:
        if not isinstance(pile, dict):
            raise ValueError('Invalid device record')
        status = str(pile.get('showStatusString', '')).strip()
        if not status:
            unknown += 1
        if status != '空闲':
            continue
        box, socket = pile.get('boxNumber'), pile.get('pileNumber')
        if box is None or socket is None or not str(box).strip() or not str(socket).strip():
            missing += 1
            continue
        locations.add((str(box).strip(), str(socket).strip()))

    def order(value):
        return (0, int(value)) if value.isdecimal() else (1, value)

    groups = {}
    for box, socket in sorted(locations, key=lambda pair: (order(pair[0]), order(pair[1]))):
        groups.setdefault(box, []).append(socket)
    lines = ['空闲位置（详情查询时）：']
    for box, sockets in groups.items():
        lines.append(f'  {box}号充电桩：' + '、'.join(socket + '号' for socket in sockets) + '插座')
    if not groups:
        lines.append('  详情暂未返回可定位的空闲插座')
    if missing:
        lines.append(f'  另有{missing}条空闲记录缺少完整编号，请在小程序核实。')
    if unknown:
        lines.append('  部分设备缺少状态文字，未将其判为空闲。')
    if len(locations) + missing != expected_count:
        lines.append(f'  注：汇总显示{expected_count}个空闲，详情查到{len(locations) + missing}个，状态可能刚发生变化。')
    return '\n'.join(lines)
