# Copyright 2014 MongoDB, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Post-processes Sphinx's latex output and generate PDFs from these ``tex`` files.
"""

import logging
import os
import re
import subprocess

logger = logging.getLogger('giza.content.post.latex')

from giza.content.helper import edition_check
from giza.tools.transformation import process_page
from giza.tools.files import create_link, copy_if_needed
from giza.tools.transformation import decode_lines_from_file, encode_lines_to_file

#################### PDFs from Latex Produced by Sphinx  ####################

def _render_tex_into_pdf(fn, deployed_path, path, output_format="pdf"):
    """
    Runs ``pdflatex`` operations, can generate ``dvi`` and ``pdf``. Runs
    pdflatex multiple times to correctly index and cross reference the PDF.
    """

    os.environ['TEXINPUTS'] = ".:{0}:".format(path)

    if output_format == 'dvi':
        pdflatex = 'pdflatex --output-format dvi --interaction batchmode --output-directory {0} {1}'.format(path, fn)
    elif output_format == 'pdf':
        pdflatex = 'pdflatex --interaction batchmode --output-directory {0} {1}'.format(path, fn)
    else:
        logger.error('not rendering pdf because {0} is not an output format'.format(output_format))
        return

    base_fn = os.path.basename(fn)
    cmds = [ pdflatex,
             "makeindex -s {0}/python.ist {0}/{1}.idx ".format(path, base_fn[:-4]),
             pdflatex,
             pdflatex ]

    if output_format == 'dvi':
        cmds.append("cd {0}; dvipdf {1}.dvi".format(path, base_fn[:-4]))

    with open(os.devnull, 'w') as devnull:
        for idx, cmd in enumerate(cmds):
            ret = subprocess.call(args=cmd.split(),
                                  stderr=devnull,
                                  stdout=devnull)
            if ret == 0:
                logger.info('pdf completed rendering stage {0} of {1} successfully ({2}, {3}).'.format(idx, len(cmds), base_fn, ret))
                continue
            else:
                if idx <= 1:
                    logger.warning('pdf build encountered error early on {0}, continuing cautiously.'.format(base_fn))
                    continue
                else:
                    logger.error('pdf build encountered error running pdflatex, investigate on {0}. terminating'.format(base_fn))
                    logger.error(cmd)
                    return False

    pdf_fn = os.path.splitext(fn)[0] + '.pdf'
    copy_if_needed(pdf_fn, deployed_path, 'pdf')

def pdf_tasks(sconf, conf, app):
    """Adds tasks to a BuildApp() to generate all PDFs."""

    target = sconf.builder
    if 'pdfs' not in conf.system.files.data:
        return

    # a list of tuples in (compileRegex, substitution) format.
    tex_regexes = [ ( re.compile(r'(index|bfcode)\{(.*)--(.*)\}'),
                      r'\1\{\2-\{-\}\3\}'),
                    ( re.compile(r'\\PYGZsq{}'), "'"),
                    ( re.compile(r'\\code\{/(?!.*{}/|etc|usr|data|var|srv|data|bin|dev|opt|proc|24|private)'),
                      r'\code{' + conf.project.url + r'/' + conf.project.tag + r'/') ]

    # the ordering of tasks. First post-process the tex generated by sphinx:
    process_app = app.add('app')
    # then convert tex to pdf
    render_app = app.add('app')
    # then migrate to build/public/
    migrate_app = app.add('app')
    # then create symlinks for alternate named files.
    link_app = app.add('app')

    # the path that sphinx writes tex files to are are different for editions.
    if 'edition' in conf.project and conf.project.edition != conf.project.name:
        latex_dir = os.path.join(conf.paths.projectroot, conf.paths.branch_output, '-'.join((target, conf.project.edition)))
    else:
        latex_dir = os.path.join(conf.paths.projectroot, conf.paths.branch_output, target)

    deploy_path = os.path.join(conf.paths.projectroot, conf.paths.public_site_output)

    # special case operations on "offset pdfs", which use EPS images.
    if 'tags' in sconf and "offset" in sconf.tags:
        output_format = "dvi"
        sty_file = os.path.join(latex_dir, 'sphinx.sty')
        process_page(fn=sty_file,
                     output_fn=sty_file,
                     regex=(re.compile(r'\\usepackage\[pdftex\]\{graphicx\}'), r'\usepackage{graphicx}'),
                     app=process_app,
                     builder='sphinx-latex',
                     copy='ifNeeded')
    else:
        output_format = "pdf"

    for i in conf.system.files.data.pdfs:
        if edition_check(i, conf) is False:
            continue

        #compatibility shim for new/old images
        i = i.dict()
        tagged_name = i['output'][:-4] + '-' + i['tag']
        deploy_fn = tagged_name + '-' + conf.git.branches.current + '.pdf'
        link_name = deploy_fn.replace('-' + conf.git.branches.current, '')

        i['source'] = os.path.join(latex_dir, i['output'])
        i['processed'] = os.path.join(latex_dir, tagged_name + '.tex')
        i['pdf'] = os.path.join(latex_dir, tagged_name + '.pdf')
        i['deployed'] = os.path.join(deploy_path, deploy_fn)
        i['link'] = os.path.join(deploy_path, link_name)
        i['path'] = latex_dir

        # add the processing task
        process_page(i['source'], i['processed'], tex_regexes, process_app, builder='tex-munge', copy='ifNeeded')

        # add task for changing TEX to PDF.
        render_task = render_app.add('task')
        render_task.dependency = None #i['processed']
        render_task.target = i['pdf']
        render_task.job = _render_tex_into_pdf
        render_task.args = (i['processed'], i['deployed'], i['path'], output_format)

        # if needed create links.
        if i['link'] != i['deployed']:
            link_task = link_app.add('task')
            link_task.dependency = i['deployed']
            link_task.target = i['link']
            link_task.job = create_link
            link_task.args = (deploy_fn, i['link'])
