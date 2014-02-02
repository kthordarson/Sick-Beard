# -*- coding: UTF-8 -*-
# Author: Trymbill <@trymbill>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of Sick Beard.
#
# Sick Beard is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Sick Beard is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Sick Beard.  If not, see <http://www.gnu.org/licenses/>.

import re
import urllib
import urllib2
#import cookielib
import sys
import os

import sickbeard
import generic
from sickbeard.common import Quality
# from sickbeard.name_parser.parser import NameParser, InvalidNameException
from sickbeard import logger
from sickbeard import tvcache
from sickbeard import helpers
from sickbeard import show_name_helpers
from sickbeard.common import Overview
from sickbeard.exceptions import ex
from sickbeard import encodingKludge as ek
from lib import requests


class DeilduProvider(generic.TorrentProvider):

    urls = {'base_url': 'https://www.deildu.net',
            'login': 'http://deildu.net/takelogin.php',
            'search': 'http://deildu.net/browse.php?sort=seeders&type=desc&cat=0',
            }

    def __init__(self):
        generic.TorrentProvider.__init__(self, "deildu")
        self.supportsBacklog = True
        self.session = None
        self.cache = DeilduCache(self)
        self.url = 'http://deildu.net/'
        self.searchurl = self.url + 'browse.php?cat=0&search=%s&sort=seeders&type=desc'
        self.re_title_url = '<tr>.*?browse\.php.*?details\.php\?id=(?P<id>\d+).+?<b>(?P<title>.*?)</b>.+?class=\"index\" href=\"(?P<url>.*?)".+?sinnum.+?align=\"right\">(?P<seeders>.*?)</td>.*?align=\"right\">(?P<leechers>.*?)</td>.*?</tr>'

    def _doLogin(self):

        login_params = {'username': sickbeard.deildu_USERNAME,
                        'password': sickbeard.deildu_PASSWORD,
#                        'login': 'submit',
                        }

#        login_params = {'username': "",
#                        'password': "",
#                        }
#
#                        'login': 'submit',
        self.session = requests.Session()

        try:
            logger.log(u"DEBUG deildu.py _doLogin starting for user " + sickbeard.deildu_USERNAME)
            response = self.session.post(self.urls['login'], data=login_params, timeout=30)
        except Exception, e:
            logger.log(u'Unable to connect to ' + self.name + ' provider: ' + ex(e))
            return False

        if re.search('Innskr&#225;ning', response.text) or response.status_code == 401:
            logger.log(u'DEBUG deildu.py Invalid username or password for ' + self.name + ', Check your settings!')
            return False

        return True

    def isEnabled(self):
        return sickbeard.deildu

    def imageName(self):
        return 'deildu.png'

    def getQuality(self, item):

        quality = Quality.nameQuality(item[0])
        return quality

    def _reverseQuality(self, quality):

        quality_string = ''

        if quality == Quality.SDTV:
            quality_string = 'HDTV x264'
        elif quality == Quality.HDTV:
            quality_string = '720p HDTV x264'
        elif quality == Quality.HDWEBDL:
            quality_string = '720p WEB-DL'
        elif quality == Quality.HDBLURAY:
            quality_string = '720p Bluray x264'
        elif quality == Quality.FULLHDBLURAY:
            quality_string = '1080p Bluray x264'

        return quality_string

    def _get_season_search_strings(self, show, season=None):

        search_string = {'Episode': []}

        if not show:
            return []

        seasonEp = show.getAllEpisodes(season)
        wantedEp = [x for x in seasonEp if show.getOverview(x.status) in (Overview.WANTED, Overview.QUAL)]
        # If Every episode in Season is a wanted Episode then search for Season first
        if wantedEp == seasonEp:
            search_string = {'Season': [], 'Episode': []}
            for show_name in set(show_name_helpers.allPossibleShowNames(show)):
                ep_string = show_name + ' S%02d' % int(season)  # 1) ShowName SXX
                search_string['Season'].append(ep_string)

                ep_string = show_name + ' Season ' + str(season)  # 2) ShowName Season X
                search_string['Season'].append(ep_string)

        # Building the search string with the episodes we need
        for ep_obj in wantedEp:
            search_string['Episode'] += self._get_episode_search_strings(ep_obj)[0]['Episode']

        #If no Episode is needed then return an empty list
        if not search_string['Episode']:
            return []

        return [search_string]

    def _get_episode_search_strings(self, ep_obj):

        search_string = {'Episode': []}

        if not ep_obj:
            return []

        if ep_obj.show.air_by_date:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):
                ep_string = show_name_helpers.sanitizeSceneName(show_name) + ' ' + str(ep_obj.airdate)
                search_string['Episode'].append(ep_string)
        else:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):
                ep_string = show_name_helpers.sanitizeSceneName(show_name) + ' ' + sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.season, 'episodenumber': ep_obj.episode}

                search_string['Episode'].append(ep_string)

        return [search_string]

    def _doSearch(self, search_params, show=None):

#        logger.log(u"DEBUG deildu.py starting _doSearch ")
        results = []
#        items = {'Season': [], 'Episode': []}
        items = {'Season': [], 'Episode': [], 'RSS': []}

        if not self._doLogin():
            return []

        self.deildu_urls_1 = self.url + '/browse.php?cat=0&search=%s&sort=seeders&type=desc'
        for mode in search_params.keys():
            for search_string in search_params[mode]:
#                search_string = search_string.replace('.', ' ')
                search_string = search_string.encode('cp1252', 'ignore')

                searchURL = self.searchurl % (urllib.quote(search_string))
#                logger.log(u"Search url: " + searchURL)
#                logger.log(u"Search string: " + urllib.quote(search_string))

                data = self.getURL(searchURL)
#                if 'login' in data:
#                    logger.log(u"DEBUG deildu.py Login handler failed, login form or nothing returned")
                if not data:
                    logger.log(u"DEBUG deildu.py Deildu reported that no torrent was found")
                try:
                    match = re.compile(self.re_title_url, re.DOTALL).finditer(urllib.unquote(data))
                except:
                    logger.log(u"DEBUG deildu.py: vesen i regex")
                for torrent in match:
                    title = torrent.group('title').replace('_', '.').decode('cp1252')
#                    logger.log(u"deildu.py torrent match loop data1: " + str(title))
                    url = torrent.group('url').decode('cp1252')
                    id = int(torrent.group('id'))
                    seeders = int(re.sub('\D', '', torrent.group('seeders')))
                    leechers = int(re.sub('\D', '', torrent.group('leechers')))
                    if seeders == 0:
                        continue
                    if not show_name_helpers.filterBadReleases(title):
                        continue
                    if not title:
                        continue
                    item = title, self.url + url, id, seeders, leechers
                    items[mode].append(item)
            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]

        return results

    def _get_title_and_url(self, item):

        title, url, id, seeders, leechers = item

        if url:
            url = url.replace('&amp;', '&')

        return (title, url)

    def downloadResult(self, result):
        """
        Save the result to disk.
        """
        logger.log(u"DEBUG deildu.py running downloadResult ... Making sure we have a cookie for Deildu")
        logger.log(u"DEBUG deildu.py Downloading a result from " + str(self.name) + " at " + str(result.url))
#        data = self.getURL(result.url, [], dlh.cj)

        if not self._doLogin():
            return []

        data = self.getURL(result.url)
        if data is None:
            return False
        saveDir = sickbeard.TORRENT_DIR
        writeMode = 'wb'
        # use the result name as the filename
        fileName = ek.ek(os.path.join, saveDir, helpers.sanitizeFileName(result.name) + '.' + self.providerType)
        logger.log(u"Saving to " + fileName)
        try:
            fileOut = open(fileName, writeMode)
            fileOut.write(data)
            fileOut.close()
            helpers.chmodAsParent(fileName)
        except IOError, e:
            logger.log(u"Unable to save the file: " + ex(e))
            return False
        return self._verify_download(fileName)

    def getURL(self, url, headers=None, cj=None):

        if not self.session:
            self._doLogin()

        if not headers:
            headers = []
        try:
#            logger.log(u"DEBUG deildu.py running getURL ... ")
            response = self.session.get(url)
        except (urllib2.HTTPError, IOError), e:
            logger.log(u"DEBUG deildu.py excetion error from urllib2 getURL ... ")
            logger.log(u"Error loading " + self.name + " URL: " + str(sys.exc_info()) + " - " + ex(e))
            return None
        return response.content


class DeilduCache(tvcache.TVCache):

    def __init__(self, provider):
        tvcache.TVCache.__init__(self, provider)
        # only poll Deildu every 10 minutes max
        self.minTime = 10

    def updateCache(self):
#        logger.log(u"DEBUG deildu.py in DeilduCache ...")
        re_title_url = self.provider.re_title_url

        if not self.shouldUpdate():
            return
#        logger.log(u"DEBUG deildu.py in DeilduCache calling _getData ... ")
        data = self._getData()

        # as long as the http request worked we count this as an update
        if data:
            self.setLastUpdate()
        else:
            return []

        # now that we've loaded the current Deildu data lets delete the old cache
        logger.log(u"DEBUG deildu.py Clearing cache..")
        self._clearCache()

        match = re.compile(re_title_url, re.DOTALL).finditer(urllib.unquote(data))
        if not match:
            logger.log(u"The Data returned from Deildu is incomplete, this result is unusable")
            return []

        for torrent in match:

            title = torrent.group('title').replace('_', '.')  # Do not know why but SickBeard skip release with '_' in name
            url = torrent.group('url')

            item = (title, url)

            self._parseItem(item)

    def _getData(self):
#        logger.log(u"DEBUG deildu.py in _getData ...")
        try:
            url = self.provider.url + 'browse.php?c12=1&c8=1&incldead=0'
#            logger.log(u"DEBUG deildu.py _getData url string: ")
        except Exception, e:
            logger.log(u"DEBUG deildu.py vesen med provider.url ... ", ex(e))
#        logger.log(u"Deildu cache update URL ")
        try:
                data = self.provider.getURL(url)
        except Exception, e:
            logger.log(u"DEBUG deildu.py vesen med provider.getURL ... ", ex(e))
        return data

    def _parseItem(self, item):
        (title, url) = item
        if not title or not url:
            return
        logger.log(u"Adding item to cache: ")
        self._addCacheEntry(title, url)

provider = DeilduProvider()
