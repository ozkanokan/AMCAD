"""Durable, opt-in GH pipeline checkpoints. No Rhino geometry or solver calls."""
import json
import os
import tempfile
import time
import uuid

TRACE_PATH = os.path.join(tempfile.gettempdir(), 'amcad-topology-trace.jsonl')


def checkpoint(stage, **data):
    record = dict(time=time.time(), pid=os.getpid(), stage=stage, **data)
    # Close each record before entering native code. The preceding START remains
    # readable from another process even while Rhino's UI thread is blocked.
    try:
        with open(TRACE_PATH, 'a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, allow_nan=False, default=str)+'\n')
            stream.flush()
    except OSError as error:
        print('AMCAD diagnostic file error: '+str(error))
    try:
        import Rhino
        Rhino.RhinoApp.WriteLine('[AMCAD trace] '+json.dumps(record, default=str))
    except ImportError:
        pass
    return record


class ComponentTrace:
    def __init__(self, component, name):
        self.name=name;self.component=str(component.InstanceGuid)
        self.run=uuid.uuid4().hex;self.started=time.perf_counter();self.context={}
        self.event('COMPONENT START')

    def event(self, stage, **data):
        return checkpoint(stage, component=self.name, component_id=self.component,
                          run=self.run, elapsed=time.perf_counter()-self.started,
                          context=dict(self.context), **data)

    def call(self, operation, function, *args, **kwargs):
        self.event('OP START', operation=operation)
        started=time.perf_counter()
        try:
            result=function(*args, **kwargs)
        except Exception as error:
            self.event('OP ERROR', operation=operation, error=repr(error));raise
        self.event('OP DONE', operation=operation, seconds=time.perf_counter()-started)
        return result

    def done(self, report):
        self.event('COMPONENT RETURN', report=list(report))


def inspect_sidecar(path):
    """Read-only recovery report; no Rhino imports, rewrite or migration."""
    with open(path, encoding='utf-8') as stream:doc=json.load(stream)
    return dict(path=os.path.abspath(path), size=os.path.getsize(path),
                schema=doc.get('schema'), groups=len(doc.get('groups', [])),
                extra_ports=doc.get('extra_ports', []), disabled=doc.get('disabled', []))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Inspect persisted topology without Rhino or GH')
    parser.add_argument('sidecar');args=parser.parse_args()
    print(json.dumps(inspect_sidecar(args.sidecar), indent=2))
