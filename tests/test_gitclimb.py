import importlib.util
import math
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location('gitclimb', Path(__file__).parents[1]/'scripts/gitclimb.py')
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)


class CalendarTests(unittest.TestCase):
    def test_empty_activity_has_no_fabricated_holds_or_animation(self):
        c=g.demo_calendar()
        for week in c['weeks']:
            for day in week['contributionDays']:
                day['contributionCount']=0
        svg,route=g.render_wall(c,'Innoffline')
        self.assertEqual(route,[])
        self.assertNotIn('<animate ',svg)
        ET.fromstring(svg)

    def test_sparse_route_never_jumps_a_gap(self):
        cells=[dict(col=x,row=r,count=n,date='unused') for x,r,n in
               [(0,6,1),(1,5,2),(2,4,1),(18,0,10),(19,1,1),(1,3,0)]]
        route=g.find_route(cells)
        self.assertEqual(len(route),3)
        self.assertTrue(all(c['count']>0 for c in route))
        for a,b in zip(route,route[1:]):
            self.assertLessEqual(math.hypot(a['col']-b['col'],a['row']-b['row']),3.1)

    def test_partial_weeks_and_54_columns(self):
        c=g.demo_calendar()
        c['weeks'][0]['contributionDays']=c['weeks'][0]['contributionDays'][3:]
        c['weeks'][-1]['contributionDays']=c['weeks'][-1]['contributionDays'][:2]
        self.assertTrue(g.normalize(c))
        c['weeks'].append({'contributionDays':[dict(date='2026-10-11',weekday=0,contributionCount=2)]})
        for theme in g.THEMES:
            svg,_=g.render_wall(c,'Innoffline',theme)
            ET.fromstring(svg)

    def test_invalid_counts_fail_and_no_token_does_not_create_demo(self):
        c=g.demo_calendar()
        c['weeks'][0]['contributionDays'][0]['contributionCount']=-1
        with self.assertRaises(ValueError): g.normalize(c)
        with self.assertRaises(ValueError): g.fetch_calendar('Innoffline','')

    def test_api_query_and_error_response(self):
        import io,json
        calendar=g.demo_calendar()
        body={'data':{'user':{'contributionsCollection':{'contributionCalendar':calendar}}}}
        with patch.object(g.urllib.request,'urlopen',return_value=io.BytesIO(json.dumps(body).encode())) as call:
            self.assertEqual(g.fetch_calendar('Innoffline','test'),calendar)
            request=call.call_args.args[0]
            self.assertEqual(json.loads(request.data)['variables']['login'],'Innoffline')
        with patch.object(g.urllib.request,'urlopen',return_value=io.BytesIO(b'{"errors":[{"message":"denied"}]}')):
            with self.assertRaisesRegex(ValueError,'denied'): g.fetch_calendar('Innoffline','test')

    def test_svg_uses_native_animation_and_equal_size_holds(self):
        svg,route=g.render_wall(g.demo_calendar(),'Innoffline',demo=True)
        root=ET.fromstring(svg)
        ns={'s':'http://www.w3.org/2000/svg'}
        self.assertGreater(len(route),1)
        self.assertTrue(root.findall('.//s:animateTransform',ns))
        self.assertNotIn('<script',svg)
        self.assertIn('sample data',svg)
        for animation in root.findall('.//s:animate',ns)+root.findall('.//s:animateTransform',ns):
            times=animation.get('keyTimes').split(';')
            self.assertEqual(len(times),len(animation.get('values').split(';')))
            self.assertEqual(float(times[0]),0)
            self.assertEqual(float(times[-1]),1)


if __name__=='__main__': unittest.main()
