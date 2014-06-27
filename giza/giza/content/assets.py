import logging
import os.path

logger = logging.getLogger('giza.content.assets')

from giza.git import GitRepo
from giza.files import rm_rf

def assets_setup(path, branch, repo):
    if os.path.exists(path):
        g = GitRepo(path)
        g.pull(branch=branch)
        logger.info('updated {0} repository'.format(path))
    else:
        base, name = os.path.split(path)

        g = GitRepo(base)

        g.clone(repo, repo_path=name, branch=branch)
        logger.info('cloned {0} branch from repo {1}'.format(branch, repo))


def assets_tasks(conf, app):
    if conf.assets is not None:
        for asset in conf.assets:
            path = os.path.join(conf.paths.projectroot, asset.path)

            logger.debug('adding asset resolution job for {0}'.format(path))

            t = app.add('task')
            t.job = assets_setup
            t.args = { 'path': path,
                       'branch': asset.branch,
                       'repo': asset.repository }

def assets_clean(conf, app):
    if conf.assets is not None:
        for asset in conf.assets:
            path = os.path.join(conf.paths.projectroot, asset.path)

            logger.debug('adding asset cleanup {0}'.format(path))

            t = app.add('task')
            t.job = rm_rf
            t.args = [path]
