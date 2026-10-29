#!/usr/bin/env python3
"""Exercise atomic publication and stale-lease rejection using real local Git repos."""
from pathlib import Path
import subprocess
import tempfile
from update import output,publish,run

with tempfile.TemporaryDirectory(prefix='noipc-publish-test-') as temp:
    base=Path(temp);remote=base/'remote.git';repo=base/'source';archive=base/'archive';state=base/'state'
    run(['git','init','--bare',remote],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run(['git','init','-b','main',repo],stdout=subprocess.DEVNULL)
    for key,value in (('user.name','Fixture'),('user.email','test@example.invalid')):
        run(['git','-C',repo,'config',key,value])
    run(['git','-C',repo,'remote','add','origin',remote])
    (repo/'source').write_text('initial\n')
    run(['git','-C',repo,'add','.']);run(['git','-C',repo,'commit','-m','Initial'],stdout=subprocess.DEVNULL)
    initial=output(['git','-C',repo,'rev-parse','HEAD'])
    run(['git','-C',repo,'push','origin','HEAD:main','HEAD:apt'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (repo/'source').write_text('updated\n')
    run(['git','-C',repo,'commit','-am','Update'],stdout=subprocess.DEVNULL)
    main=output(['git','-C',repo,'rev-parse','HEAD'])
    archive.mkdir();(archive/'Packages').write_text('current only\n');state.mkdir()
    apt=publish(repo,archive,state,initial,initial)
    assert output(['git','--git-dir',remote,'rev-parse','main'])==main
    assert output(['git','--git-dir',remote,'rev-list','--count','main'])=='2'
    assert output(['git','--git-dir',remote,'rev-list','--count','apt'])=='1'
    assert output(['git','--git-dir',remote,'ls-tree','--name-only','apt'])=='Packages'
    print('PASS: atomic publication retains source history and replaces APT with one current snapshot')
    # Another writer moves apt; the old expected hash must refuse BOTH updates.
    run(['git','-C',repo,'push','--force','origin',f'{initial}:apt'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (repo/'source').write_text('third\n');run(['git','-C',repo,'commit','-am','Third'],stdout=subprocess.DEVNULL)
    try: publish(repo,archive,state,main,apt)
    except subprocess.CalledProcessError: pass
    else: raise AssertionError('Stale lease unexpectedly succeeded')
    assert output(['git','--git-dir',remote,'rev-parse','main'])==main
    assert output(['git','--git-dir',remote,'rev-parse','apt'])==initial
    print('PASS: a stale APT lease rejects publication atomically and preserves both remote refs')
print('All atomic publication checks passed; no external repository was modified.')
