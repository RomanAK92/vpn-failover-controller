"""Build the exact legacy installer's copied assets in an owned disposable image.

No systemd installation, host port, VPN configuration or network change.
"""
import argparse
import importlib.util
import json
import pathlib
import secrets
import shutil
import subprocess
import tempfile


def main(source):
    source=pathlib.Path(source).resolve()
    spec=importlib.util.spec_from_file_location('copied_dashboard_installer',source/'dashboard/install.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    image='vpn-dashboard-package-'+secrets.token_hex(4)+':test'
    def command(*args,timeout=30):
        result=subprocess.run(args,text=True,capture_output=True,timeout=timeout)
        if result.returncode:raise RuntimeError('Owned copied-package check failed: '+args[0])
        return result.stdout
    try:
        with tempfile.TemporaryDirectory(prefix='vpn-dashboard-package-') as directory:
            target=pathlib.Path(directory)
            for name in module.FILES:
                shutil.copyfile(source/'dashboard'/name,target/name);(target/name).chmod(0o644)
            command('docker','build','-t',image,str(target),timeout=600)
            command('docker','run','--rm','--network','none','--user','65532:65532',
                '--cap-drop','ALL','--security-opt','no-new-privileges:true','--read-only',
                '--memory','128m','--pids-limit','32','--entrypoint','python3',image,'-B','-c',
                'import pathlib,server,accounts,drafts,control,support;'
                'assert all(pathlib.Path(n).is_file() for n in '
                '("management.js","drafts.js","login.js","index.html","profiles.js"))')
    finally:
        subprocess.run(['docker','image','rm',image],capture_output=True,timeout=30)
    # Confirm the exact owned image is absent, rather than assuming cleanup worked.
    result=subprocess.run(['docker','image','inspect',image],capture_output=True,timeout=30)
    if result.returncode==0:raise RuntimeError('Owned image cleanup incomplete.')
    print(json.dumps({'result':'PASS','copied_assets_build':True,'unprivileged_runtime_imports':True,
        'owned_image_cleaned':True,'services_started':False,'host_network_changed':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',default=str(pathlib.Path(__file__).parents[1]))
    main(parser.parse_args().source)
