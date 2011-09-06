#!/usr/bin/python
# encoding: utf-8
#
# Copyright (C) 2011 by Coolman & Swiss-MAD
#
# In case of reuse of this source code please do not remove this copyright.
#
#	This program is free software: you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation, either version 3 of the License, or
#	(at your option) any later version.
#
#	This program is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	For more information on the GNU General Public License see:
#	<http://www.gnu.org/licenses/>.
#
import math
import os
from collections import defaultdict
from time import time
from datetime import datetime

from Components.config import *
from Components.GUIComponent import GUIComponent
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest, MultiContentEntryProgress
from Tools.LoadPixmap import LoadPixmap
from Tools.Directories import fileExists
from skin import parseColor, parseFont, parseSize
from enigma import eListboxPythonMultiContent, eListbox, gFont, RT_HALIGN_LEFT, RT_HALIGN_RIGHT, RT_HALIGN_CENTER, eServiceReference, eServiceCenter
from timer import TimerEntry

from RecordingsControl import RecordingsControl
from DelayedFunction import DelayedFunction
from EMCTasker import emcDebugOut
from EnhancedMovieCenter import _
from VlcPluginInterface import VlcPluginInterfaceList, vlcSrv, vlcDir, vlcFil
from operator import itemgetter
from CutListSupport import CutList
from MetaSupport import MetaList
from EitSupport import EitList
from PermanentSort import PermanentSort


global extAudio, extDvd, extVideo, extPlaylist, extList, extMedia
global cmtDir, cmtUp, cmtTrash, cmtLRec, cmtVLC, cmtBM, virVLC, virAll
global vlcSrv, vlcDir, vlcFil
global plyDVB, plyM2TS, plyDVD, plyMP3, plyVLC, plyAll
global sidDVB, sidDVD, sidMP3


# Set definitions

# Media types
extAudio    = frozenset([".ac3", ".dts", ".flac", ".m4a", ".mp2", ".mp3", ".ogg", ".wav"])
extVideo    = frozenset([".ts", ".avi", ".divx", ".f4v", ".flv", ".img", ".iso", ".m2ts", ".m4v", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".mts", ".vob"])
extPlaylist = frozenset([".m3u"])
extMedia    = extAudio | extVideo | extPlaylist
extDir      = frozenset([""])
extList     = extMedia | extDir

# Additional file types
extTS       = frozenset([".ts"])
extM2ts     = frozenset([".m2ts"])
extDvd      = frozenset([".iso", ".img", ".ifo"])
extVLC      = frozenset([vlcFil])

# Player types
plyDVB      = extTS																		# ServiceDVB
plyM2TS     = extM2ts																	# ServiceM2TS
plyDVD      = extDvd																	# ServiceDVD
plyMP3      = extMedia - plyDVB - plyM2TS - plyDVD		# ServiceMP3 GStreamer
plyVLC      = extVLC																	# VLC Plugin
plyAll      = plyDVB | plyM2TS | plyDVD | plyMP3 | plyVLC


# Type definitions

# Service ID types for E2 service identification
sidDVB      = eServiceReference.idDVB									# eServiceFactoryDVB::id   enum { id = 0x1 }; 
sidDVD      = 4369 																		# eServiceFactoryDVD::id   enum { id = 0x1111 };
sidMP3      = 4097																		# eServiceFactoryMP3::id   enum { id = 0x1001 };
# For later purpose
sidM2TS     = 3 																			# eServiceFactoryM2TS::id  enum { id = 0x3 };
#TODO
#sidXINE = 4112										# eServiceFactoryXine::id  enum { id = 0x1010 };
#additionalExtensions = "4098:m3u 4098:e2pls 4098:pls"

# Grouped service ids
sidsCuts = frozenset([sidDVB, sidDVD])

# Custom types (Used by EMC internally)
cmtDir     = "DIR"
cmtUp      = "UP"
cmtTrash   = "TRASH"
cmtLRec    = "LREC"
cmtVLC     = "VLC"
cmtBM      = "BM"

# Grouped custom types
virVLC     = frozenset([cmtVLC, vlcSrv, vlcDir])
virAll     = frozenset([cmtBM, cmtVLC, cmtLRec, cmtTrash, cmtUp, cmtDir, vlcSrv, vlcDir])

#-------------------------------------------------
# func: readBasicCfgFile( file )
#
# Reads the lines of a file in a list. Empty lines
# or lines beginnig with '#' will be ignored.
#-------------------------------------------------
def readBasicCfgFile(file):
	data = []
	f = None
	try:
		f = open(file, "r")
		lines = f.readlines()
		for line in lines:
			line = line.strip()
			if not line:					# no empty lines
				continue
			if line[0:1] == "#":				# no comment lines
				continue
			data.append( line )
	except Exception, e:
		emcDebugOut("[EMC] Exception in readBasicCfgFile: " + str(e))
	finally:
		if f is not None:
			f.close()
	return data


class MovieCenter(GUIComponent, VlcPluginInterfaceList, PermanentSort):
	instance = None
	
	def __init__(self):
		MovieCenter.instance = self
		self.list = []
		GUIComponent.__init__(self)
		VlcPluginInterfaceList.__init__(self)
		PermanentSort.__init__(self)
		self.loadPath = config.EMC.movie_homepath.value
		self.serviceHandler = eServiceCenter.getInstance()
		
		self.alphaSort = config.EMC.CoolStartAZ.value
		self.returnSort = None
		
		self.CoolFont = parseFont("Regular;20", ((1,1),(1,1)))
		self.CoolSelectFont = parseFont("Regular;20", ((1,1),(1,1)))
		self.CoolDateFont = parseFont("Regular;20", ((1,1),(1,1)))
		
		self.CoolMoviePos = 100
		self.CoolMovieSize = 490
		self.CoolFolderSize = 550
		self.CoolTitleColor = 0
		self.CoolDatePos = -1
		self.CoolDateWidth = 110
		self.CoolDateColor = 0
		self.CoolHighlightColor = 0
		self.CoolProgressPos = -1
		self.CoolBarPos = -1
		self.CoolBarHPos = 8
		
		self.CoolBarSize = parseSize("55,10", ((1,1),(1,1)))
		self.CoolBarSizeSa = parseSize("55,10", ((1,1),(1,1)))
		
		self.DateColor = 0xFFFFFF
		self.DefaultColor = 0xFFFFFF
		self.BackColor = None
		self.BackColorSel = 0x000000
		self.FrontColorSel = 0xFFFFFF
		self.UnwatchedColor = 0xFFFFFF
		self.WatchingColor = 0x3486F4
		self.FinishedColor = 0x46D93A
		self.RecordingColor = 0x9F1313
		#IDEA self.CutColor
		
		self.l = eListboxPythonMultiContent()
		self.l.setFont(0, gFont("Regular", 22))
		self.l.setFont(1, self.CoolFont)
		self.l.setFont(2, gFont("Regular", 20))
		self.l.setFont(3, self.CoolSelectFont)
		self.l.setFont(4, self.CoolDateFont)
		self.l.setBuildFunc(self.buildMovieCenterEntry)
		self.l.setItemHeight(28)
		self.currentSelectionCount = 0		
		
		self.selectionList = None
		self.recControl = RecordingsControl(self.recStateChange)
		self.highlightsMov = []
		self.highlightsDel = []
		
		self.pic_back            = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/back.png')
		self.pic_directory       = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dir.png')
		self.pic_movie_default   = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_default.png')
		self.pic_movie_unwatched = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_unwatched.png')
		self.pic_movie_watching  = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_watching.png')
		self.pic_movie_finished  = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_finished.png')
		self.pic_movie_rec       = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_rec.png')
		self.pic_movie_recrem    = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_recrem.png')
		self.pic_movie_cut       = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/movie_cut.png')
		self.pic_bookmark        = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/bookmark.png')
		self.pic_trashcan        = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/trashcan.png')
		self.pic_trashcan_full   = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/trashcan_full.png')
		self.pic_mp3             = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/music.png')
		self.pic_dvd_default     = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dvd_default.png')
		self.pic_dvd_watching    = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dvd_watching.png')
		self.pic_dvd_finished    = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/dvd_finished.png')
		self.pic_playlist        = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/playlist.png')
		self.pic_vlc             = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/vlc.png')
		self.pic_vlc_dir         = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/vlcdir.png')
		self.pic_link            = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/link.png')
		self.pic_latest          = LoadPixmap(cached=True, path='/usr/lib/enigma2/python/Plugins/Extensions/EnhancedMovieCenter/img/virtual.png')
		
		self.onSelectionChanged = []
		self.hideitemlist = []
		if config.EMC.cfghide_enable.value:
			self.hideitemlist = readBasicCfgFile("/etc/enigma2/emc-hide.cfg")
		self.nostructscan = []
		if config.EMC.cfgnoscan_enable.value:
			self.nostructscan = readBasicCfgFile("/etc/enigma2/emc-noscan.cfg")
		
		# Initially load the movielist
		# So it must not be done when the user it opens the first time
		#MAYBE this should be configurable
		DelayedFunction(10000, self.reload, self.loadPath)

	def applySkin(self, desktop, parent):
		attribs = []
		if self.skinAttributes is not None:
			for (attrib, value) in self.skinAttributes:
				if attrib == "CoolFont":
					self.CoolFont = parseFont(value, ((1,1),(1,1)))
					self.l.setFont(1, self.CoolFont)
				elif attrib == "CoolSelectFont":
					self.CoolSelectFont = parseFont(value, ((1,1),(1,1)))
					self.l.setFont(3, self.CoolSelectFont)
				elif attrib == "CoolDateFont":
					self.CoolDateFont = parseFont(value, ((1,1),(1,1)))
					self.l.setFont(4, self.CoolDateFont)
				elif attrib == "CoolDirPos":
					pass
				
				elif attrib == "CoolMoviePos":
					self.CoolMoviePos = int(value)
				elif attrib == "CoolMovieSize":
					self.CoolMovieSize = int(value)
				elif attrib == "CoolFolderSize":
					self.CoolFolderSize = int(value)
				elif attrib == "CoolTitleColor":
					self.CoolTitleColor = int(value)
				elif attrib == "CoolDatePos":
					self.CoolDatePos = int(value)
				elif attrib == "CoolDateWidth":
					self.CoolDateWidth = int(value)
				elif attrib == "CoolDateColor":
					self.CoolDateColor = int(value)
				elif attrib == "CoolHighlightColor":
					self.CoolHighlightColor = int(value)
				elif attrib == "CoolTimePos":
					pass
				
				elif attrib == "CoolProgressPos":
					self.CoolProgressPos = int(value)
				elif attrib == "CoolBarPos":
					self.CoolBarPos = int(value)
				elif attrib == "CoolBarHPos":
					self.CoolBarHPos = int(value)
				elif attrib == "CoolBarSize":
					self.CoolBarSize = parseSize(value, ((1,1),(1,1)))
				elif attrib == "CoolBarSizeSa":
					self.CoolBarSizeSa = parseSize(value, ((1,1),(1,1)))
				elif attrib == "DefaultColor":
					self.DefaultColor = parseColor(value).argb()
				elif attrib == "BackColor":
					self.BackColor = parseColor(value).argb()
				elif attrib == "BackColorSel":
					self.BackColorSel = parseColor(value).argb()
				elif attrib == "FrontColorSel":
					self.FrontColorSel = parseColor(value).argb()
				elif attrib == "UnwatchedColor":
					self.UnwatchedColor = parseColor(value).argb()
				elif attrib == "WatchingColor":
					self.WatchingColor = parseColor(value).argb()
				elif attrib == "FinishedColor":
					self.FinishedColor = parseColor(value).argb()
				elif attrib == "RecordingColor":
					self.RecordingColor = parseColor(value).argb()
				else:
					attribs.append((attrib, value))
		self.skinAttributes = attribs
		return GUIComponent.applySkin(self, desktop, parent)

	def selectionChanged(self):
		for f in self.onSelectionChanged:
			try:
				f()
			except Exception, e:
				emcDebugOut("[MC] External observer exception: \n" + str(e))

	def setSorting(self, trueOrFalse):
		self.returnSort = None
		self.alphaSort = trueOrFalse
		
		self.list = self.doListSort(self.list)
		self.l.setList( self.list )

	def getSorting(self):
		perm = self.getPermanentSort(self.loadPath)
		if perm is not None:
			perm = self.alphaSort == perm
		# Return the actual sorting mode and if the current sorting mode is set as the permanent one
		return ( self.alphaSort, perm )

	def doListSort(self, sortlist):
		# This will find all unsortable items
		# But is not as fast as the second implementation
		# If [2] = date = None then it is a directory or special folder entry
		tmplist = [i for i in sortlist if not i[2]]
		# Extract list items to be sorted
		sortlist = sortlist[len(tmplist):]
		
		# Find only the first items which won't be sorted
#		i = 0
#		for e in xrange(len(sortlist)):
#			# If [2] = date = None then it is a directory or special folder entry
#			if sortlist[e][2]:
#				i=e
#				break
#		# Copy items which won't be sorted
#		tmplist = sortlist[:i]
#		# Copy items which will be sorted
#		sortlist = sortlist[i:]
		
		# Sort list, same algorithm for both implementations
		# Using itemgetter is slightly faster but not as flexible
		# Then the list has to be flat, no sub tuples were allowed (key=itemgetter(x))
		if self.alphaSort:
			sortlist.sort( key=lambda x: (x[1][0]), reverse=config.EMC.moviecenter_reversed.value )
		else:
			sortlist.sort( key=lambda x: (x[1][1]), reverse=not config.EMC.moviecenter_reversed.value )
			#Faster if separate? sortlist.reverse()
			
			#TEST
				# Create sortkeys
				#sorttitle = title.lower()
				#sortkeyalpha = sorttitle + cutnr + sortdate
				#cutnrreverse = str( 999 - int(cutnr or 0) )
				
				#sorttitle = title.lower() #without cut_nr
				#cutnr = int(cutnr or 0)
				#append((service, sorttitle, date, title, path, 0, length, ext)) ,cutnr
				
				#sortkeydate = date + sorttitle + str( 999 - int(cutnr or 0) 
			#sortlist.sort( key=lambda x: (x[2],x[1],-x[8]))
		
		# Combine lists
		return tmplist + sortlist

	def recStateChange(self, timer):
		if timer:
			path = os.path.dirname(timer.Filename)
			if path == self.loadPath:
				# EMC shows the directory which contains the recording
				if timer.state == TimerEntry.StateRunning:
					if not self.list:
						# Empty list it will be better to reload it complete
						# Maybe EMC was never started before
						emcDebugOut("[MC] Timer started - full reload")
						DelayedFunction(3000, self.reload, self.loadPath)
					else:
						# We have to add the new recording
						emcDebugOut("[MC] Timer started - add recording")
						# Timer filname is without extension
						filename = timer.Filename + ".ts"
						DelayedFunction(3000, self.reload, filename)
				elif timer.state == TimerEntry.StateEnded:
					#MAYBE Just refresh the ended record
					# But it is fast enough
					emcDebugOut("[MC] Timer ended")
					DelayedFunction(3000, self.refreshList)
# 			#WORKAROUND Player is running during a record ends
# 			# We should find a more flexible universal solution
# 			from MovieSelection import gMS
# 			if gMS and gMS.playerInstance is not None:
# 				DelayedFunction(3000, self.updatePlayer)
# 
# 	def updatePlayer(self):
# 		from MovieSelection import gMS
# 		if gMS and gMS.playerInstance is not None:
# 			gMS.playerInstance.updateCuesheet(gMS)

	def getProgress(self, service, length=0, last=0, forceRecalc=False, cuts=None):
		# All calculations are done in seconds
		# The progress of a recording isn't correct, because we only get the actual length not the final
		cuts = None
		progress = 0
		updlen = length
		if last <= 0:
			# Get last position from cut file
			if cuts is None:
				cuts = CutList( service.getPath() )
			last = cuts.getCutListLast()
		# Check for valid position
		if last > 0 or forceRecalc:
			# Valid position
			# Recalc the movie length to calculate the progress status
			if length <= 0: 
				if service:
					length = self.getLengthFromServiceHandler(service)
				if length <= 0: 
					if cuts is None:
						cuts = CutList( service.getPath() )
					length = cuts.getCutListLength()
					if length <= 0: 
						# Set default file length if is not calculateable
						# 90 minutes = 90 * 60
						length = 5400
						# We only update the entry if we do not use the default value
						updlen = 0
					else:
						updlen = length
				else:
					updlen = length
				if updlen:
					self.updateLength(service, updlen)
			if length:
				progress = self.calculateProgress(last, length)
			else:
				# This should never happen, we always have our default length
				progress = 100
				#emcDebugOut("[MC] getProgress(): Last without any length")
		else:
			# No position implies progress is zero
			progress = 0
		return progress

	def getRecordProgress(self, path):
		# The progress of all recordings is updated
		# - on show dialog
		# - on reload list / change directory / movie home
		# The progress of one recording is updated
		# - if it will be highlighted the list
		# Note: There is no auto update mechanism of the recording progress
		begin, end = self.recControl.getRecordingTimes(path)
		last = time() - begin
		length = end - begin
		return self.calculateProgress(last, length)

	def calculateProgress(self, last, length):
		progress = 0
		if length:
			# Adjust the watched movie length (98% of movie length) 
			# else we will never see the 100%
			adjlength = float(length) / 100.0 * 98.0
			# Calculate progress and round up
			progress = int( math.ceil ( float(last) / float(adjlength) * 100.0 ) )
			# Normalize progress
			if progress < 0: progress = 0
			elif progress > 100: progress = 100
		return progress

	def updateLength(self, service, length):
		# Update entry in list... so next time we don't need to recalc
		idx = self.getIndexOfService(service)
		if idx >= 0:
			x = self.list[idx]
			if x[6] != length:
				l = list(x)
				l[6] = length
				self.list[idx] = tuple(l)

	def dirInfo(self, path):
		count = 0
		if os.path.exists(path):
			for p in os.listdir(path):
				pext = os.path.splitext(p)[1]
				if pext in extList:
					count += 1
		return count

	def buildMovieCenterEntry(self, service, sortkeys, date, title, path, selnum, length, ext):
		#TODO remove before release
		try:
			offset = 0
			progressWidth = 55
			globalHeight = 40
			progress = 0
			pixmap = None
			color = None
			
			res = [ None ]
			append = res.append
			
			isLink = os.path.islink(path)
			usedFont = int(config.EMC.skin_able.value)
			
			#TODO ret print "EMC bldSer " +str(service.toString())
			
			if ext in plyAll:
				colortitle = None
				colordate = None
				colorhighlight = None
				selnumtxt = None
				
				# Playable files
				latest = date and (datetime.today()-date).days < 1
				
				# Check for recording only if date is within the last day
				if latest and self.recControl.isRecording(path):
					date = "-- REC --"
					pixmap = self.pic_movie_rec
					color = self.RecordingColor
					# Recordings status shows always the progress of the recording, 
					# Never the progress of the cut list marker to avoid misunderstandings
					progress = service and self.getRecordProgress(path) or 0
				
				elif latest and config.EMC.remote_recordings.value and self.recControl.isRemoteRecording(path):
					date = "-- rec --"
					pixmap = self.pic_movie_recrem
					color = self.RecordingColor
				
				#IDEA elif config.EMC.check_movie_cutting.value:
				elif self.recControl.isCutting(path):
					date = "-- CUT --"
					pixmap = self.pic_movie_cut
					color = self.RecordingColor
				
				elif ext in plyVLC:
					date = "   VLC   "
					pixmap = self.pic_vlc
					color = self.DefaultColor
				
				else:
					# Media file
					date = date.strftime( config.EMC.movie_date_format.value )
					progress = service and self.getProgress(service, length) or 0
					
					# Progress State
					movieUnwatched = config.EMC.movie_mark.value and	progress < int(config.EMC.movie_watching_percent.value)
					movieWatching  = config.EMC.movie_mark.value and	progress >= int(config.EMC.movie_watching_percent.value) and progress < int(config.EMC.movie_finished_percent.value)
					movieFinished  = config.EMC.movie_mark.value and	progress >= int(config.EMC.movie_finished_percent.value)
					
					# Icon
					# video
					if ext in extVideo:
						if movieUnwatched:
							if not latest:
								pixmap = self.pic_movie_unwatched
							else:
								pixmap = self.pic_latest
						elif movieWatching:
							pixmap = self.pic_movie_watching
						elif movieFinished:
							pixmap = self.pic_movie_finished
						else:
							pixmap = self.pic_movie_default
					# audio
					elif ext in extAudio:
						pixmap = self.pic_mp3
					# dvd iso or structure
					elif ext in extDvd:
						if movieWatching:
							pixmap = self.pic_dvd_watching
						elif movieFinished:
							pixmap = self.pic_dvd_finished
						else:
							pixmap = self.pic_dvd_default
					# playlists
					elif ext in extPlaylist:
						pixmap = self.pic_playlist
					# all others
					else:
						pixmap = self.pic_movie_default
					
					# Color
					if movieUnwatched:
						color = self.UnwatchedColor
					elif movieWatching:
						color = self.WatchingColor
					elif movieFinished:
						color = self.FinishedColor
					else:
						color = self.DefaultColor
				
				# Skin color handling
				if self.CoolTitleColor == 0:
					colortitle = self.DefaultColor
				else:
					colortitle = color
				
				if self.CoolDateColor == 0:
					colordate = self.DateColor
				else:
					colordate = color
				
				if self.CoolHighlightColor == 0:
					colorhighlight = self.FrontColorSel
				else:
					colorhighlight = color
				
				# Get entry selection number
				if selnum == 9999: selnumtxt = "-->"
				elif selnum == 9998: selnumtxt = "X"
				elif selnum > 0: selnumtxt = "%02d" % selnum
				if service in self.highlightsMov: selnumtxt = "-->"
				elif service in self.highlightsDel: selnumtxt = "X"
				
				# Is there any way to combine it for both files and directories?
				if config.EMC.movie_icons.value and selnumtxt is None:
					append(MultiContentEntryPixmapAlphaTest(pos=(5,2), size=(24,24), png=pixmap, **{}))
					if isLink:
						append(MultiContentEntryPixmapAlphaTest(pos=(7,13), size=(9,10), png=self.pic_link, **{}))
					offset = 35
				if selnumtxt is not None:
					append(MultiContentEntryText(pos=(5, 0), size=(26, globalHeight), font=3, flags=RT_HALIGN_LEFT, text=selnumtxt))
					offset += 35
				
				if config.EMC.skin_able.value:
					if self.CoolBarPos != -1:
						append(MultiContentEntryProgress(pos=(self.CoolBarPos, self.CoolBarHPos -2), size = (self.CoolBarSizeSa.width(), self.CoolBarSizeSa.height()), percent = progress, borderWidth = 1, foreColor = color, backColor = color))
					if self.CoolProgressPos != -1:
						append(MultiContentEntryText(pos=(self.CoolProgressPos, 0), size=(progressWidth, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text="%d%%" % (progress)))
					if self.CoolDatePos != -1:
						append(MultiContentEntryText(pos=(self.CoolDatePos, 2), size=(self.CoolDateWidth, globalHeight), font=4, text=date, color = colordate, color_sel = colorhighlight, flags=RT_HALIGN_CENTER))
						
					append(MultiContentEntryText(pos=(self.CoolMoviePos, 0), size=(self.CoolMovieSize, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text=title, color = colortitle, color_sel = colorhighlight))
					return res
				
				if config.EMC.movie_progress.value == "PB":
					append(MultiContentEntryProgress(pos=(offset, self.CoolBarHPos), size = (self.CoolBarSize.width(), self.CoolBarSize.height()), percent = progress, borderWidth = 1, backColorSelected = None, foreColor = color, backColor = color))
					offset += self.CoolBarSize.width() + 10
				elif config.EMC.movie_progress.value == "P":
					append(MultiContentEntryText(pos=(offset, 0), size=(progressWidth, globalHeight), font=usedFont, flags=RT_HALIGN_CENTER, text="%d%%" % (progress), color = color, color_sel = colorhighlight, backcolor = self.BackColor, backcolor_sel = self.BackColorSel))
					offset += progressWidth + 5
				
				if config.EMC.movie_date.value:
					append(MultiContentEntryText(pos=(self.l.getItemSize().width() - self.CoolDateWidth, 0), size=(self.CoolDateWidth, globalHeight), font=4, color = colordate, color_sel = colorhighlight, backcolor = self.BackColor, backcolor_sel = self.BackColorSel, flags=RT_HALIGN_CENTER, text=date))
				append(MultiContentEntryText(pos=(offset, 0), size=(self.l.getItemSize().width() - offset - self.CoolDateWidth -5, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text=title, color = colortitle, color_sel = colorhighlight, backcolor = self.BackColor, backcolor_sel = self.BackColorSel))
			
			else:
				# Directory and vlc directories
				
				#TODO Color not used yet for folders
				#color = self.DefaultColor
				
				if ext == cmtVLC:
					date = _("VLC")
					pixmap = self.pic_vlc
				elif ext == vlcSrv:
					date = _("VLC-Server")
					pixmap = self.pic_vlc
				elif ext == vlcDir:
					date = _("VLC-Dir")
					pixmap = self.pic_vlc_dir
				elif ext == cmtLRec:
					date = _("Latest")
					pixmap = self.pic_latest
				elif ext == cmtUp:
					date = _("Up")
					pixmap = self.pic_back
				elif ext == cmtBM:
					date = _("Bookmark")
					pixmap = self.pic_bookmark
				elif ext in cmtTrash:
					if config.EMC.movie_trashcan_dynamic.value:
						count = self.dirInfo(path)
						if count:
							# Trashcan contains garbage
							pixmap = self.pic_trashcan_full
						else:
							# Trashcan is empty
							pixmap = self.pic_trashcan
						date = " ( %d ) " % (count)
					else:
						pixmap = self.pic_trashcan
						date = "Trashcan"
				elif ext == cmtDir:
					if config.EMC.directories_info.value:
						count = self.dirInfo(path)
						date = " ( %d ) " % (count)
					else:
						date = _("Directory")
					pixmap = self.pic_directory
				else:
					pixmap = self.pic_directory
					date = _("UNKNOWN")
									
				# Is there any way to combine it for both files and directories?
				append(MultiContentEntryPixmapAlphaTest(pos=(5,2), size=(24,24), png=pixmap, **{}))
				if isLink:
					append(MultiContentEntryPixmapAlphaTest(pos=(7,13), size=(9,10), png=self.pic_link, **{}))
				# Directory left side
				append(MultiContentEntryText(pos=(30, 0), size=(self.CoolFolderSize, globalHeight), font=usedFont, flags=RT_HALIGN_LEFT, text=title))
				# Directory right side
				append(MultiContentEntryText(pos=(self.l.getItemSize().width() - self.CoolDateWidth, 0), size=(self.CoolDateWidth, globalHeight), font=2, flags=RT_HALIGN_CENTER, text=date))
			
			del append
			return res
		except Exception, e:
			emcDebugOut("[EMCMS] build exception:\n" + str(e))

	def getCurrent(self):
		l = self.l.getCurrentSelection()
		return l and l[0]

	def getCurrentIndex(self):
		return self.instance.getCurrentIndex()

	def getCurrentEvent(self):
		l = self.l.getCurrentSelection()
		if l and l[0]:
			info = self.serviceHandler.info(l[0])
			return info and info.getEvent(l[0])

	GUI_WIDGET = eListbox

	def postWidgetCreate(self, instance):
		instance.setWrapAround(True)
		instance.setContent(self.l)
		instance.selectionChanged.get().append(self.selectionChanged)

	def removeService(self, service):
		if service:
			for l in self.list[:]:
				if l[0] == service:
					self.list.remove(l)
			self.l.setList(self.list)

	def addService(self, service):
		#TODO
		# Actually You can only use reload with filname
		pass

	def serviceBusy(self, service):
		return service in self.highlightsMov or service in self.highlightsDel

	def serviceMoving(self, service):
		return service and service in self.highlightsMov

	def serviceDeleting(self, service):
		return service and service in self.highlightsDel

	def highlightService(self, enable, mode, service):
		if enable:
			if mode == "move":
				self.highlightsMov.append(service)
				self.toggleSelection(service, overrideNum=9999)
			elif mode == "del":
				self.highlightsDel.append(service)
				self.toggleSelection(service, overrideNum=9998)
		else:
			if mode == "move":
				self.highlightsMov.remove(service)
			elif mode == "del":
				self.highlightsDel.remove(service)

	def __len__(self):
		return len(self.list)

	def makeSelectionList(self):
		selList = []
		if self.currentSelectionCount == 0:
			# if no selections made, select the current cursor position
			single = self.l.getCurrentSelection()
			if single:
				selList.append(single[0])
		else:
			selList = self.selectionList
		return selList

	def resetSelection(self):
		self.selectionList = None
		self.currentSelectionCount = 0

	def unselectService(self, service):
		if service:
			if self.selectionList:
				if service in self.selectionList:
					# Service is in selection - unselect it
					self.toggleSelection(service)
				else:
					self.invalidateService(service)
			else:
				self.invalidateService(service)

	def toggleSelection(self, service=None, index=-1, overrideNum=None):
		x = None
		if service is None:
			if index == -1:
				if self.l.getCurrentSelection() is None: return
				index = self.getCurrentIndex()
			x = self.list[index]
		else:
			index = 0
			for e in self.list:
				if e[0] == service:
					x = e
					break
				index += 1
		if x is None: return
		
		# We have x=service, index, overrideNum
		if self.indexIsDirectory(index): return
		if self.selectionList == None:
			self.selectionList = []
		newselnum = x[5]	# init with old selection number
		if overrideNum == None:
			if self.serviceBusy(x[0]): return	# no toggle if file being operated on
			# basic selection toggle
			if newselnum == 0:
				# was not selected
				self.currentSelectionCount += 1
				newselnum = self.currentSelectionCount
				self.selectionList.append(x[0]) # append service
			else:
				# was selected, reset selection number and decrease all that had been selected after this
				newselnum = 0
				self.currentSelectionCount -= 1
				count = 0
				if x is not None:
					self.selectionList.remove(x[0]) # remove service
				for i in self.list:
					if i[5] > x[5]:
						l = list(i)
						l[5] = i[5]-1
						self.list[count] = tuple(l)
						self.l.invalidateEntry(count) # force redraw
					count += 1
		else:
			newselnum = overrideNum * (newselnum == 0)
		l = list(x)
		l[5] = newselnum
		self.list[index] = tuple(l)
		self.l.invalidateEntry(index) # force redraw of the modified item

	def getLengthFromServiceHandler(self, service):
		# Get the movie length in seconds
		if service:
			info = self.serviceHandler.info(service)
			if info:
				return info.getLength(service)
			else:
				return 0
		else:
			return 0

	def getFilePathOfService(self, service):
		if service:
			for entry in self.list:
				if entry[0] == service:
					return entry[4]
		return ""

	def getNameOfService(self, service):
		if service:
			for entry in self.list:
				if entry[0] == service:
					return entry[3]
		return ""

	def getLengthOfService(self, service):
		if service:
			for entry in self.list:
				if entry[0] == service:
					return entry[6]
		return 0

	def getIndexOfService(self, service):
		if service:
			idx = 0
			for entry in self.list:
				if entry[0] == service:
					return idx
				idx += 1
		return -1
	
	def getServiceOfIndex(self, index):
		return self.list[index] and self.list[index][0]
	
	def invalidateCurrent(self):
		self.l.invalidateEntry(self.getCurrentIndex())

	def invalidateService(self, service):
		idx = self.getIndexOfService(service)
		if idx < 0: return
		self.l.invalidateEntry( idx ) # force redraw of the item

	def detectDVDStructure(self, checkPath):
		if not os.path.isdir(checkPath):
			return None
		elif config.EMC.noscan_linked.value and os.path.islink(checkPath):
			return None
		dvdpath = os.path.join(checkPath, "VIDEO_TS.IFO")
		if fileExists( dvdpath ):
			return dvdpath
		dvdpath = os.path.join(checkPath, "VIDEO_TS/VIDEO_TS.IFO")
		if fileExists( dvdpath ):
			return dvdpath
		return None
	
	def createDirList(self, loadPath):
		subdirlist, filelist = [], []
		dvdStruct = None
		pathname, ext = "", ""
		
		# Improve performance and avoid dots
		movie_trashpath = config.EMC.movie_trashpath.value
		check_dvdstruct = config.EMC.check_dvdstruct.value and loadPath not in self.nostructscan
		hideitemlist = self.hideitemlist
		localExtList = extList
		
		dappend = subdirlist.append
		fappend = filelist.append
		splitext = os.path.splitext
		pathjoin = os.path.join
		pathisfile = os.path.isfile
		pathisdir = os.path.isdir
		
		if os.path.exists(loadPath):
			
			# Get directory listing
			for p in os.listdir(loadPath):
				
				# This will decrease the function execution time massively
				ext = splitext(p)[1].lower()
				if ext not in localExtList:
					continue
				
				if hideitemlist:
					if p in hideitemlist or (p[0:1] == "." and ".*" in hideitemlist):
						continue
				
				pathname = pathjoin(loadPath, p)
				
				if pathisfile(pathname):
					# Media file found
					# Check is done implizit with in listDir and isfile
					# Avoid retesting ( if ext in extMedia )
					fappend( (pathname, p, ext) )
				
				elif pathisdir(pathname):
					
					# Display folders capitalized
					p.capitalize()
					
					if check_dvdstruct:
						dvdStruct = self.detectDVDStructure(pathname)
						if dvdStruct:
							# DVD Structure found
							pathname = os.path.dirname(dvdStruct)
							ext = splitext(dvdStruct)[1].lower()
							fappend( (pathname, p, ext) )
							continue
					
					# Folder found
					if pathname != movie_trashpath and config.EMC.directories_show.value:
						dappend( (pathname, p, cmtDir) )
				
				else:
					# We have found a dead link
					# Can be a file or folder
					#IDEA: Display them optionally?
					pass
		
		del dappend
		del fappend
		del splitext
		del pathjoin
		del pathisfile
		del pathisdir
		return subdirlist, filelist

	def createLatestRecordingsList(self):
		# Make loadPath more flexible
		#MAYBE: What about using current folder for latest recording lookup?
		dirstack, subdirlist, filelist, subfilelist = [], [], [], []
		
		# walk through entire tree below movie home. Might take a bit long on huge disks...
		# think about breaking at 2nd level,
		# but include folders used in timers, auto timers and bookmarks
		dirstack.append(config.EMC.movie_homepath.value)
		
		# Search files through all given paths
		while dirstack:
			
			# Get entries
			subdirlist, subfilelist = self.createDirList( dirstack.pop() )
			
			# Found new directories to search within, use only their path
			dirstack.extend( [i[0] for i in subdirlist] )
			
			# Store the media files
			filelist.extend( subfilelist )
		
		# Sorting is done through our default sorting algorithm
		return filelist

	def createFileInfo(self, pathname):
		# Create info for new record
		p = os.path.basename(pathname)
		ext = os.path.splitext(p)[1].lower()
		return [ (pathname, p, ext) ]

	def createCustomList(self, loadPath, trashcan=True, extend=True):
		customlist = []
		path, name = "", ""
		append = customlist.append
		pathjoin = os.path.join
		pathnormpath = os.path.normpath
		pathbasename = os.path.basename
		
		if loadPath != "" and loadPath != config.EMC.movie_pathlimit.value:
			append( (	pathjoin(loadPath, ".."),
								"..",
								cmtUp) )
		
		if extend:
			# Insert these entries always at last
			if loadPath == config.EMC.movie_homepath.value:
				if trashcan and config.EMC.movie_trashcan_enable.value and config.EMC.movie_trashcan_show.value:
					append( (	config.EMC.movie_trashpath.value,
										(pathbasename(config.EMC.movie_trashpath.value)).capitalize(),
										cmtTrash) )
				
				if config.EMC.latest_recordings.value:
					append( (	pathjoin(loadPath, "Latest Recordings"),
										"Latest Recordings",
										cmtLRec) )
				
				if config.EMC.vlc.value and os.path.exists("/usr/lib/enigma2/python/Plugins/Extensions/VlcPlayer"):
					append( (	pathjoin(loadPath, "VLC servers"),
										"VLC servers",
										cmtVLC) )
				
				if config.EMC.bookmarks_e2.value:
					if config.movielist and config.movielist.videodirs:
						bookmarks = [pathnormpath(e2bm) for e2bm in config.movielist.videodirs.value]
						if bookmarks:
							for bookmark in bookmarks:
								append( (	bookmark,
													"E2 "+(pathbasename(bookmark).capitalize()),
													cmtBM) )
		
		del append
		del pathjoin
		del pathnormpath
		del pathbasename
		return customlist

	def reload(self, loadPath, simulate=False):
		emcDebugOut("[MC] LOAD PATH:\n" + str(loadPath))
		customlist, subdirlist, filelist, tmplist = [], [], [], []
		resetlist = True 
		dosort = True
		alphaSort = None
		
		if config.EMC.remote_recordings.value:
			# get a list of current remote recordings
			self.recControl.recFilesRead()
		
		# Create listings
		if os.path.isdir(loadPath):
			# Found directory
			
			# Read subdirectories and filenames
			subdirlist, filelist = self.createDirList(loadPath)
			customlist = self.createCustomList(loadPath)
		
		elif os.path.isfile(loadPath):
			# Found file
			
			filelist = self.createFileInfo(loadPath)
			resetlist = False
			loadPath = None
			
		else:
			# Found virtual directory
			
			if loadPath.endswith("VLC servers"):
				emcDebugOut("[EMC] VLC Server")
				subdirlist = self.createVlcServerList(loadPath)
				customlist = self.createCustomList(loadPath, extend=False)
			
			elif loadPath.find("VLC servers")>-1:
				emcDebugOut("[EMC] VLC Files")
				subdirlist, filelist = self.createVlcFileList(loadPath)
			
			elif loadPath.endswith("Latest Recordings"):
				emcDebugOut("[EMC] Latest Recordings")
				filelist = self.createLatestRecordingsList()
				customlist = self.createCustomList(loadPath, extend=False)
				# Set date sort mode
				alphaSort = False
			
			else:
				# No changes done
				return False
		
		# Local variables
		movie_metaload = config.EMC.movie_metaload.value
		movie_eitload = config.EMC.movie_eitload.value
		movie_hide_mov = config.EMC.movie_hide_mov.value
		movie_hide_del = config.EMC.movie_hide_del.value
		movie_show_cutnr = config.EMC.movie_show_cutnr.value
		movie_show_format = config.EMC.movie_show_format.value
		
		# Avoid dots
		append = tmplist.append
		pathexists = os.path.exists
		pathgetmtime = os.path.getmtime
		
		# Add custom entries and sub directories to the list
		customlist += subdirlist
		if customlist is not None:
			for path, filename, ext in customlist:
				service = self.getPlayerService(path, filename)
				#TODO sorting keys
				append((service, (None, None), None, filename, path, 0, 0, ext))
		
		# Add file entries to the list
		if filelist is not None:
			for path, filename, ext in filelist:
				# Filename, Title, Date, Sortingkeys handling
				# First we extract as much as possible informations from the filename
				service = None
				title, date, time, cutnr = "", "", "", ""
				length = 0
				metastring, eitstring = "", ""
				metadate, eitdate = "", ""
				sorttitle, sortdate = "", ""
				sortkeyalpha, sortkeydate = "", ""
				
				# Remove extension
				if not ext:
					# Avoid splitext it is very slow compared to a slice
					title, ext = os.path.splitext(filename)
				else:
					#TODO Should not be necessary
					# If there is an ext filename is already the shortname without the extension
					title = filename[:-len(ext)]
					
				# Get cut number
				if title[-4:-3] == "_" and title[-3:].isdigit():
					cutnr = title[-3:]
					title = title[:-4]
				
				# Replace underscores with spaces
				title = title.replace("_"," ")
				
				# Derived from RecordTimer
				# This is everywhere so test it first
				if title[0:8].isdigit():
					if not title[8:9].isdigit() and title[9:13].isdigit():
						# Default: filename = YYYYMMDD TIME - service_name
						sortdate = title[0:13]							# "YYYYMMDD TIME - " -> "YYYYMMDD TIME"
						title = title[16:]									# skips "YYYYMMDD TIME - "
						
						# Standard: filename = YYYYMMDD TIME - service_name - name
						# Long Composition: filename = YYYYMMDD TIME - service_name - name - description
						# Standard: filename = YYYYMMDD TIME - service_name - name
						# Skip service_name, extract name
						split = title.find(" - ")
						if split > 0: title = title[3+split:]
						
					elif title[8:11] == " - ":
						# Short Composition: filename = YYYYMMDD - name
						sortdate = title[0:8] + " 2000"			# "YYYYMMDD" + " " + DUMMY_TIME
						title = title[11:]									# skips "YYYYMMDD - "
					
					time = int(sortdate[9:13])
					date = int(sortdate[0:8])
					date = datetime(date/10000, date%10000/100, date%100, time/100, time%100)
				
				# If the user wants it, extract information from the meta and eit files
				
				if movie_metaload and service:
					# read title from META
					meta = MetaList(path)
					if meta:
						metastring = meta.getMetaName()
						print "EMC Meta metastring " +str(metastring)
						#TEST date
						#if not date:
						metadate = meta.getMetaRecordingTime()  # Time in seconds since 1970
						print "EMC Meta rectime " +str(metadate)
						# Improve performance and avoid calculation of movie length
						length = meta.getMetaLength()
						print "EMC Meta length  " +str(length)
				
				if not metastring and movie_eitload and service:
						# read title from EIT
						eit = EitList(path)
						if eit:
							eitstring = eit.getEitName()
							print "EMC eit eitstring: " + str(eitstring)
							#if not date:
							eitdate = eit.getEitWhen()+" "+eit.getEitStartDate()+" "+eit.getEitStartTime()  # Time in seconds since 1970 ?!?
							print "EMC eit eitdate " +str(eitdate)
							#if not length:
							length = eit.getEitLengthInSeconds()
							print "EMC eit length: " + str(length)
				
				# Priority and fallback handling
				
				# Set title priority here
				# Fallback is the filename
				title = metastring or eitstring or title or filename
				
				# Very bad but there can be both encodings
				# E2 recordings are always in utf8
				# User files can be in cp1252
				# Is there no other way?
				try:
					title.decode('utf-8')
				except UnicodeDecodeError:
					title = title and title.decode("cp1252").encode("utf-8")
				
				# Set date priority here
				# Fallback get date from filesystem, but it is very slow
				#date = date #TODO or metadate or eitdate or os.path.exists(path) and datetime.fromtimestamp( os.path.getmtime(path) ) or None
				date = date or metadate or (pathexists(path) and datetime.fromtimestamp( pathgetmtime(path) )) or None
				
				# Create sortkeys
				if not sortdate: sortdate = date and date.strftime( "%Y%m%d%H%M" ) or ""
				sorttitle = title.lower()
				sortkeyalpha = sorttitle + cutnr + sortdate
				#cutnrreverse = str( 999 - int(cutnr or 0) )
				sortkeydate = sortdate + sorttitle + str( 999 - int(cutnr or 0) )
				
				# combine information regarding the emc config
				if movie_show_cutnr:
					title += " "+cutnr
				
				if movie_show_format:
					title += " "+ext[1:]
				
				# Get player service and set formatted title
				service = self.getPlayerService(path, title, ext)
				
				# Check config settings
				#TODO These checks should be done earlier but there we don't have the service yet
				if (movie_hide_mov and self.serviceMoving(service)) \
					or (movie_hide_del and self.serviceDeleting(service)):
					continue
				
				append((service, (sortkeyalpha, sortkeydate), date, title, path, 0, length, ext))
		
		# Cleanup before continue
		del append
		del pathexists
		del pathgetmtime
		
		if not simulate:
			# If we are here, there is no way back
			self.currentSelectionCount = 0
			self.selectionList = None
			
			if loadPath is not None:
				self.loadPath = loadPath
				
				# Lookup for a permanent sorting mode
				permSort = self.getPermanentSort(loadPath)
				if permSort is not None:
					# Backup the actual sorting mode
					if self.returnSort is None:
						self.returnSort = self.alphaSort
					self.alphaSort = permSort
				
				elif self.returnSort is not None:
					# Restore sorting mode
					self.alphaSort = self.returnSort
					self.returnSort = None
				
				if alphaSort is not None:
					# Backup the actual sorting mode
					if self.returnSort is None:
						self.returnSort = self.alphaSort
					# Set new sorting mode
					self.alphaSort = alphaSort
		
			if resetlist:
				self.list = []
			else:
				tmplist = self.list + tmplist
		
			if dosort:
				# Do list sort
				self.list = self.doListSort( tmplist )
			else:
				self.list = tmplist
			
			# Assign list to listbox
			self.l.setList( self.list )
		
		else:
			# Simulate only
			tmplist = self.doListSort( tmplist )
			return tmplist
		
		return True

	def refreshList(self):
		# Just invalidate the whole list to force rebuild the entries 
		# Updates the progress of all entries
		#IDEA Extend the list and mark the recordings 
		# so we don't have to go through the whole list
		#TEST Performance for recordings only updating
		#     Separate function for updating recordings only
		#     Check for recording only if date is within the last day
		#for entry in self.list:
		#	if self.recControl.isRecording(entry[4]):
		#		self.invalidateService(entry[0])
		self.l.invalidate()

	def getNextService(self):
		#IDEA: Optionally loop over all
		if self.currentSelIsPlayable():
			# Cursor marks a movie
			idx = self.getCurrentIndex()
			length = len(self.list)
			for i in xrange(length):
				entry = self.list[(i+idx)%length]
				if entry:
					if entry[2]: 
						# Entry is no directory
						service = entry[0]
						if not self.serviceMoving(service) and not self.serviceDeleting(service):
							yield service
		elif self.currentSelIsDirectory():
			# Cursor marks a directory
			#IDEA: Optionally play also the following movielist items (folders and movies)
			path = self.getCurrentSelDir()
			# Don't play movies from the trash folder or ".."
			if path != config.EMC.movie_trashpath.value and path != "..":
				#IDEA Is there a way to reuse the reload or createdirlist function
					#TODO Then the files are sorted and played in their correct order
					# So we don't have the whole dir and file recognition handling twice
					# Simulate reload:	tmplist = self.reload(path, True)
				for root, dirs, files in os.walk(path): #,False):
					if dirs:
						for dir in dirs:
							path = os.path.join(root, dir)
							dvdStruct = self.detectDVDStructure( path )
							if dvdStruct:
								path = os.path.dirname(dvdStruct)
								ext = os.path.splitext(dvdStruct)[1].lower()
								service = self.getPlayerService(path, dir, ext)
								if not self.serviceMoving(service) and not self.serviceDeleting(service):
									yield service
					if files:
						for name in files:
							ext = os.path.splitext(name)[1].lower()
							if ext in extMedia:
								path = os.path.join(root, name)
								#TODO get formatted Name
								service = self.getPlayerService(path, name, ext)
								if not self.serviceMoving(service) and not self.serviceDeleting(service):
									yield service

	def getPlayerService(self, path, name="", ext=None):
		if ext in plyDVB:
			service = eServiceReference(sidDVB, 0, path)
		elif ext in plyMP3:
			service = eServiceReference(sidMP3, 0, path)
		elif ext in plyDVD:
			service = eServiceReference(sidDVD, 0, path)
			#QUESTION Is the special name handling really necessary
			if service:
				# Copied from dvd player
				if path.endswith("/VIDEO_TS") or path.endswith("/"):
					names = service.toString().rsplit("/",3)
					if names[2].startswith("Disk ") or names[2].startswith("DVD "):
						#TEST name = str(names[1]) + " - " + str(names[2])
						name = names[1] + " - " + names[2]
					else:
						name = names[2]
					#TEST service.setName(str(name))
					#service.setName(name)
		elif ext in plyM2TS:
			service = eServiceReference(sidM2TS, 0, path)
		else:
			service = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + path)
		if name:
			service.setName(name)
		else:
			service.setName( os.path.basename(path).capitalize() )
		return service

	def currentSelIsPlayable(self):
		try:	return self.list[self.getCurrentIndex()][7] in extMedia
		except:	return False

	def currentSelIsDirectory(self):
		try:	return self.list[self.getCurrentIndex()][7] == cmtDir
		except:	return False

	def currentSelIsVirtual(self):
		try:	return self.list[self.getCurrentIndex()][7] in virAll
		except:	return False

	def currentSelIsBookmark(self):
		try:	return self.list[self.getCurrentIndex()][7] == cmtBM
		except:	return False

	def indexIsDirectory(self, index):
		try:	return self.list[index][7] == cmtDir
		except:	return False

	def getCurrentSelDir(self):
		try:	return self.list[self.getCurrentIndex()][4]
		except:	return False

	def getCurrentSelName(self):
		try: return self.list[self.getCurrentIndex()][3]
		except: return "none"

	def moveToIndex(self, index):
		self.instance.moveSelectionTo(index)

	def moveToService(self, service):
		if service:
			for c, x in enumerate(self.list):
				if x[0] == service:
					self.instance.moveSelectionTo(c)
					break
