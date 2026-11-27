import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('workflow_graph', ROOT / 'library/skills/workflow-graph/scripts/render.py')
graph = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(graph)


class WorkflowGraphTests(unittest.TestCase):
    def test_committed_bundle_is_current(self):
        graph.build(ROOT / 'docs/architecture', check=True)

    def test_visible_steps_are_validated_in_each_numbered_view(self):
        def svg(*labels):
            root = ET.Element(f'{{{graph.SVG}}}svg')
            for label in labels:
                node = ET.SubElement(root, f'{{{graph.SVG}}}g', {'class': 'node workflow-step'})
                ET.SubElement(node, f'{{{graph.SVG}}}text').text = label
            return root
        graph.check_numbers(svg('1 · Input', '2a · Run', '2b · Skip', '3 · Finish'), 'fixture')
        for labels in [('Input',), ('1 · Input', '1 · Again'), ('1 · Input', '3 · Skip'), ('1b · Start',)]:
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                graph.check_numbers(svg(*labels), 'fixture')
        directory = ROOT / 'docs/architecture'
        manifest = graph.views_for(directory)
        self.assertTrue(manifest['numbered'])
        viewer = (directory / 'index.html').read_text()
        for number, view in enumerate(manifest['views'], 1):
            graph.check_numbers(ET.parse(directory / (view['id'] + '.svg')).getroot(), view['id'])
            self.assertIn(f'View {number} ·', viewer)

    @unittest.skipUnless(shutil.which('dot'), 'requires Graphviz for new layouts')
    def test_renders_another_project_and_detects_staleness_without_rerendering(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            source = project / 'docs'
            source.mkdir()
            (project / 'app.py').write_text('def run(): return 42\n')
            views = [
                dict(id='overview', title='Service & UI', description='Request to response.',
                     evidence=[dict(label='Entrypoint', path='../app.py')]),
                dict(id='worker', title='Worker', description='Validate the job and save its result.'),
            ]
            manifest = source / 'workflow.json'
            manifest.write_text(json.dumps({'title': 'Example', 'views': views}))
            (source / 'overview.dot').write_text('digraph { client -> worker; worker [URL="index.html#worker",target="_top"] }')
            detail = source / 'worker.dot'
            detail.write_text('digraph { validate -> save }')
            graph.build(source)
            graph.build(source, check=True)
            viewer = (source / 'index.html').read_text()
            self.assertIn('Service &amp; UI', viewer)
            self.assertIn('href="#worker"', viewer)
            self.assertEqual(ET.parse(source / 'worker.svg').getroot().tag, f'{{{graph.SVG}}}svg')
            detail.write_text('digraph {')
            with self.assertRaisesRegex(ValueError, 'Stale'):
                graph.build(source, check=True)
            with self.assertRaisesRegex(ValueError, 'worker.dot'):
                graph.build(source)
            self.assertEqual(viewer, (source / 'index.html').read_text())
            detail.write_text('digraph { validate -> save }')
            (source / 'index.html').write_text('stale viewer')
            with self.assertRaisesRegex(ValueError, 'Stale offline viewer'):
                graph.build(source, check=True)
            views.pop()
            manifest.write_text(json.dumps({'title': 'Example', 'views': views}))
            (source / 'overview.dot').write_text('digraph { client -> output }')
            unrelated = source / 'logo.svg'
            unrelated.write_text('<svg/>')
            with self.assertRaisesRegex(ValueError, 'Obsolete'):
                graph.build(source, check=True)
            graph.build(source)
            self.assertFalse((source / 'worker.svg').exists())
            self.assertEqual(unrelated.read_text(), '<svg/>')
            (project / 'app.py').unlink()
            with self.assertRaisesRegex(ValueError, 'evidence'):
                graph.build(source, check=True)


if __name__ == '__main__':
    unittest.main()
