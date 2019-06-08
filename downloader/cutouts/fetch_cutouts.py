# system
import os
import sys

# utilities
import re
import click
import yaml as yml

# astropy
from astropy.io import fits

# threading
import threading
import queue

# configuration
from surveys.survey_config import SurveyConfig


# kills a thread when given into the queue
class PoisonPill:
    def __init__(self):
        pass


# A thread that grabs data from a queue, processes, then optionally tosses into another queue
class WorkerThread(threading.Thread):
    def __init__(self, work, input_q, output_q=None, *args, **kwargs):
        self.input_q = input_q
        self.output_q = output_q
        self.work = work
        super().__init__(*args, **kwargs)

    def run(self):
        while True:
            work_in = self.input_q.get()

            # if it's swallowed
            if type(work_in) is PoisonPill:
                self.input_q.task_done()
                return

            ret = self.work(work_in)
            self.input_q.task_done()

            if self.output_q:
                self.output_q.put(item=ret)


# grab a FITS hdu from some survey
def get_cutout(target):
    target['hdu'] = target['survey'].get_cutout(target['coord'], target['size'])
    return target


# save an HDU into a file
def save_cutout(target):
    if target['hdu']:
        target['hdu'].writeto("{0}".format(target['filename']), overwrite=True)
    else:
        survey = type(target['survey']).__name__
        msg_str = f"cutout at {target['coord']} returned None"
        prefix_msg_str = "\n".join([f"{survey}: {s}" for s in msg_str.splitlines()])
        print(prefix_msg_str)


@click.command()
@click.option('--config-file',default='config.yml',help='yaml search parameters configuration file')
def batch_process(config_file="config.yml"):
    """Survey Cutout fetching script (cf., config.yml)"""


    print(f"Using Configuration: {config_file}")
    cfg = SurveyConfig(config_file)

    grabbers = 10
    savers = 1

    # set up i/o queues
    # TODO: Add ctrl-c queues sigkill...
    in_q  = queue.Queue()
    out_q = queue.Queue()

    # toss all the targets into the queue, including for all surveys
    # i.e., some position in both NVSS and VLASS and SDSS, etc.
    for task in cfg.get_procssing_stack():
        in_q.put(task)

    # spin up a bunch of worker threads to process all the data
    # in principle these could be chained further, such that you could go
    # targets -> hdus -> save to file -> process to jpg -> save to file
    for _ in range(grabbers):
        WorkerThread(get_cutout, in_q, out_q).start()
        in_q.put(PoisonPill())

    # testing out 1 save to file threads (absolutely not necessary)
    for _ in range(savers):
        WorkerThread(save_cutout, out_q).start()
    in_q.join()

    for _ in range(savers):
        out_q.put(PoisonPill())
    out_q.join()


if __name__ == "__main__":
    batch_process()