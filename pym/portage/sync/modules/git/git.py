# Copyright 2005-2015 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2

import logging
import subprocess

import portage
from portage import os
from portage.util import writemsg_level
from portage.output import create_color_func
good = create_color_func("GOOD")
bad = create_color_func("BAD")
warn = create_color_func("WARN")
from portage.sync.syncbase import NewBase


class GitSync(NewBase):
	'''Git sync class'''

	short_desc = "Perform sync operations on git based repositories"

	@staticmethod
	def name():
		return "GitSync"


	def __init__(self):
		NewBase.__init__(self, "git", portage.const.GIT_PACKAGE_ATOM)


	def exists(self, **kwargs):
		'''Tests whether the repo actually exists'''
		return os.path.exists(os.path.join(self.repo.location, '.git'))


	def new(self, **kwargs):
		'''Do the initial clone of the repository'''
		if kwargs:
			self._kwargs(kwargs)
		try:
			if not os.path.exists(self.repo.location):
				os.makedirs(self.repo.location)
				self.logger(self.xterm_titles,
					'Created new directory %s' % self.repo.location)
		except IOError:
			return (1, False)

		sync_uri = self.repo.sync_uri
		if sync_uri.startswith("file://"):
			sync_uri = sync_uri[6:]

		git_cmd_opts = ""
		if self.settings.get("PORTAGE_QUIET") == "1":
			git_cmd_opts += " --quiet"
		if self.repo.sync_depth is not None:
			git_cmd_opts += " --depth %d" % self.repo.sync_depth
			#required with shallow cloning to see all the other branches
			#with git branch --all
			git_cmd_opts += " --no-single-branch"
		if self.repo.module_specific_options.get('sync-git-clone-extra-opts'):
			git_cmd_opts += " %s" % self.repo.module_specific_options['sync-git-clone-extra-opts']
		if self.repo.sync_branch is not None:
			git_cmd_opts += " -b %s" % self.repo.sync_branch
		git_cmd = "%s clone%s %s ." % (self.bin_command, git_cmd_opts,
			portage._shell_quote(sync_uri))
		writemsg_level(git_cmd + "\n")

		exitcode = portage.process.spawn_bash("cd %s ; exec %s" % (
				portage._shell_quote(self.repo.location), git_cmd),
			**self.spawn_kwargs)
		if exitcode != os.EX_OK:
			msg = "!!! git clone error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		return (os.EX_OK, True)

	def nuke_repo(self):
		'''removes the repository'''
		rm_cmd = "rm -rf"
		writemsg_level(rm_cmd + " " + self.repo.location + "\n")
		exitcode = portage.process.spawn_bash("%s %s" % (rm_cmd, 
				portage._shell_quote(self.repo.location)))
		if exitcode != os.EX_OK:
			msg = "!!! Error running rm -rf  %s" % self.repo.location
			msg += "!!! Please remove %s manually" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)
		return (os.EX_OK, True)

	def sync_branch_update(self):
		'''switches a git repository branch to match the value set by sync-branch
		if it is unable to switch to the correct branch it will stay at the old
		branch'''
		git_cmd = "cd %s && git branch --all" % self.repo.location
		try:
			rawbranch = subprocess.check_output(git_cmd, shell=True, \
				universal_newlines=True)
		except subprocess.CalledProcessError:
			return os.EX_NOTFOUND, True
		for branchline in rawbranch.split("\n"):
			blist = branchline.strip().split()
			if blist[0] == "*":
				if blist[1] == self.repo.sync_branch:
					return self.simple_update() #we're at the correct branch
			elif "/" not in blist[0]:
				if blist[0] == self.repo.sync_branch: #branch exists locally, checkout
					git_cmd = "cd %s && git checkout %s" % \
						(self.repo.location, self.repo.sync_branch)
					try:
						subprocess.check_output(git_cmd, shell=True)
					except subprocess.CalledProcessError:
						return self.simple_update()
					return self.simple_update()
			elif not "HEAD" in blist[0] and "/" in blist[0]: #branch exists remotely
				branchl = blist.split("/")
				if branchl[2] == self.repo.sync_branch: #found the correct value
					git_cmd = "cd %s && git checkout -b %s" % \
						(self.repo.location, self.repo.sync_branch)
					git_cmd += " --track origin/%s" % self.repo.sync_branch
					try:
						subprocess.check_output(git_cmd, shell=True)
					except subprocess.CalledProcessError:
						return self.simple_update()
					return self.simple_update()
		#There should be a big red warning here that the branch doesn't exist
		#if we get to this point. Instead we'll just sync the branch for now
		return self.simple_update()

	def sync_uri_check(self):
		'''checks that self.repo.sync_uri matches the output of git remote -v i.e.
		checks if git and repos.conf agree on what the sync-uri value is
		'''
		git_cmd = "cd %s && git remote -v" % self.repo.location
		try:
			rawremote = subprocess.check_output(git_cmd, shell=True, \
				universal_newlines=True)
		except subprocess.CalledProcessError:
			return False
		for remoteline in rawremote.split("\n"):
			rlist = remoteline.split()
			if rlist[0] == "origin" and rlist[2] == "(fetch)":
				return self.repo.sync_uri == rlist[1]

	def simple_update(self):
		''' Update existing git repository, and ignore the sync-uri by default. We are
		going to trust the user and assume that the user is in the branch
		that he/she wants updated. We'll let the user manage branches with
		git directly.
		'''
		git_cmd_opts = ""
		if self.settings.get("PORTAGE_QUIET") == "1":
			git_cmd_opts += " --quiet"
		if self.repo.module_specific_options.get('sync-git-pull-extra-opts'):
			git_cmd_opts += " %s" % self.repo.module_specific_options['sync-git-pull-extra-opts']
		git_cmd = "%s pull%s" % (self.bin_command, git_cmd_opts)
		writemsg_level(git_cmd + "\n")

		rev_cmd = [self.bin_command, "rev-list", "--max-count=1", "HEAD"]
		previous_rev = subprocess.check_output(rev_cmd,
			cwd=portage._unicode_encode(self.repo.location))

		exitcode = portage.process.spawn_bash("cd %s ; exec %s" % (
				portage._shell_quote(self.repo.location), git_cmd),
			**self.spawn_kwargs)
		if exitcode != os.EX_OK:
			msg = "!!! git pull error in %s" % self.repo.location
			self.logger(self.xterm_titles, msg)
			writemsg_level(msg + "\n", level=logging.ERROR, noiselevel=-1)
			return (exitcode, False)

		current_rev = subprocess.check_output(rev_cmd,
			cwd=portage._unicode_encode(self.repo.location))

		return (os.EX_OK, current_rev != previous_rev)

	def update(self):
		'''However, if auto-sync-enforcing = yes is set, portage will enforce
		that the values in the repos.conf files match the ones in the git repositories,
		and will automagically update the git repositories.
		'''
		if self.repo.auto_sync_enforcing == "no" or self.repo.auto_sync_enforcing is None:
			return self.simple_update()
		else:
			#Check sync-uri first. If sync-uri doesn't match, nuke the git repository
			#and start from scratch. This will automagically set the correct 
			#sync-branch option
			if self.repo.sync_uri is not None and self.repo.location is not None:
				if not self.sync_uri_check():
					self.nuke_repo()
					return self.new()
			#If sync-uri matches, check that sync-branch matches too. Otherwise,
			#switch to the correct branch. 
			if self.repo.sync_branch is not None and self.repo.location is not None:
				return self.sync_branch_update()
			return self.simple_update()
