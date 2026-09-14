import unittest
from render import raw_time, cursor


class TimelineTests(unittest.TestCase):
    def test_cut_mapping_starts_at_a_nonzero_capture_epoch(self):
        scene={"start":100,"end":140,"cuts":[[104,110],[115,119]]}
        self.assertEqual(raw_time(scene,2),102)
        self.assertEqual(raw_time(scene,4),110)
        self.assertEqual(raw_time(scene,10),120)
        self.assertEqual(raw_time(scene,100),140)

    def test_pointer_never_jumps_before_actual_action(self):
        events=[{"kind":"move","t0":20,"t1":22,"from":[60,60],"to":[100,200]}]
        self.assertEqual(cursor(events,19),(60,60))
        self.assertEqual(cursor(events,20.5),(70,95))
        self.assertEqual(cursor(events,21),(80,130))
        self.assertEqual(cursor(events,25),(100,200))


if __name__=="__main__":unittest.main()
