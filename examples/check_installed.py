"""Run the full suite and CLI replay from a wheel outside the checkout."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv

ROOT = Path(__file__).resolve().parents[1]
ENV = os.environ.copy()
ENV.pop('PYTHONPATH', None)
ENV.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1')
MODULES = ['ratinglab', 'ratinglab.__main__', 'ratinglab.batch', 'ratinglab.batch_export',
           'ratinglab.controls', 'ratinglab.core', 'ratinglab.dataset',
           'ratinglab.experiment', 'ratinglab.export', 'ratinglab.influence']
COMMANDS = [
    ('ratinglab', ['report']), ('ratinglab', ['controls']), ('ratinglab', ['audit']),
    ('ratinglab', ['witness']), ('ratinglab', ['predict', '--input', 'samples.json']),
    ('ratinglab', ['fit', '--output', 'fresh.json']),
    ('ratinglab', ['audit', '--report', 'fresh.json']),
    ('ratinglab', ['batch', '--input', 'examples/batch.json']),
    ('ratinglab', ['batch-export']), ('ratinglab.influence', ['demo']),
    ('ratinglab.influence', ['references', '--output', 'influence-reference.json']),
]


def call(args, cwd, env=ENV):
    return subprocess.check_output(args, cwd=cwd, env=env, text=True)


with tempfile.TemporaryDirectory() as directory:
    work = Path(directory)
    wheels = work / 'wheels'
    wheels.mkdir()
    call([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '-w', str(wheels),
          str(ROOT)], work)
    built = list(wheels.glob('*.whl'))
    assert len(built) == 1, built
    venv.create(work / 'env', with_pip=True)
    py = str(work / 'env/bin/python')
    call([py, '-m', 'pip', 'install', str(built[0])], work)
    outside = work / 'outside'
    outside.mkdir()
    for name in ['tests', 'examples', 'assets', 'docs']:
        shutil.copytree(ROOT / name, outside / name)
    # The tests read these archive paths. No library Python files are copied.
    shutil.copytree(ROOT / 'ratinglab/artifacts', outside / 'ratinglab/artifacts')
    suite = '''
import importlib,importlib.util,json,pathlib,sys,unittest
outside=pathlib.Path.cwd().resolve()
sys.path.insert(0,str(outside))
names=json.loads(sys.argv[1])
source=pathlib.Path(sys.argv[2]).resolve()
prefix=pathlib.Path(sys.prefix).resolve()
for name in names:importlib.import_module(name)
def check():
    for name in names:
        origin=pathlib.Path(importlib.util.find_spec(name).origin).resolve()
        assert origin.is_relative_to(prefix),(name,str(origin))
        assert not origin.is_relative_to(source),(name,str(origin))
        assert 'site-packages' in origin.parts,(name,str(origin))
check()
tests=unittest.defaultTestLoader.discover(str(outside/'tests'))
result=unittest.TextTestRunner(verbosity=2).run(tests)
assert result.testsRun>0 and result.wasSuccessful()
check()
print(json.dumps(dict(tests=result.testsRun,installed_origins=len(names),
                     checked_before_and_after=True)))
'''
    print(call([py, '-I', '-c', suite, json.dumps(MODULES), str(ROOT)], outside))
    reference = work / 'reference'
    reference.mkdir()
    shutil.copytree(ROOT / 'examples', reference / 'examples')
    source_env = ENV.copy()
    source_env['PYTHONPATH'] = str(ROOT)
    samples = json.dumps({'pairs': [[0, 0], [137, 129]]})
    for folder in [reference, outside]:
        (folder / 'samples.json').write_text(samples)
    reports = 0
    for module, args in COMMANDS:
        expected = json.loads(call([sys.executable, '-m', module] + args,
                                   reference, source_env))
        actual = json.loads(call([py, '-I', '-m', module] + args, outside))
        assert actual == expected, (module, args)
        reports += 1
    for name in ['fresh.json', 'influence-reference.json']:
        assert json.loads((outside / name).read_text()) == json.loads((reference / name).read_text()), name
    print(json.dumps(dict(complete_reports=reports, main_command_kinds=8,
                          influence_commands=2, complete_output_files=2,
                          fresh_models=11, reproduced_figures=1,
                          entrypoint='python -m')))
