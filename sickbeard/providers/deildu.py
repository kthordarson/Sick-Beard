# -*- coding: UTF-8 -*-a
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
import cookielib
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

cookie_filename = "deildu.cookies"


class DeilduLoginHandler(object):

    def __init__(self):
        """ Start up... """
        self.login = sickbeard.DEILDU_USERNAME
        self.password = sickbeard.DEILDU_PASSWORD
        logger.log("from config, login: " + str(self.login), logger.DEBUG)
        logger.log("from config, pw: " + str(self.password), logger.DEBUG)


        self.cj = cookielib.MozillaCookieJar(cookie_filename)
        # check if we can access cookie, and make sure it's not empty
        if os.access(cookie_filename, os.F_OK) and os.path.getsize(cookie_filename) > 0:
            self.cj.load()
        self.opener = urllib2.build_opener(
            urllib2.HTTPRedirectHandler(),
            urllib2.HTTPHandler(debuglevel=1),
            urllib2.HTTPSHandler(debuglevel=1),
            urllib2.HTTPCookieProcessor(self.cj)
        )
        self.opener.addheaders = [
            ('User-agent', ('Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.2; .NET CLR 1.1.4322)'))
        ]

        # need this twice - once to set cookies, once to log in...
        self.loginToDeildu()
        self.loginToDeildu()

        self.cj.save()

    def loginToDeildu(self):
        """
        Handle login. This should populate our cookie jar.
        """

        login_data = urllib.urlencode({
            'username': self.login,
            'password': self.password,
        })
        response = self.opener.open("http://deildu.net/takelogin.php", login_data)
#        if response:
#            for line in response:
#                tempdeb01 = line.encode('utf8')
#                logger.log(u"deilduresponse: " + tempdeb01, logger.DEBUG)
#            tempdeb01 = response.read()
#            logger.log("logintodeildu got response from deildu" + str(tempdeb01), logger.DEBUG)
#
#        else:
#            logger.log("logintodeildu no response from edildu", logger.DEBUG)
        return response

    def loggedIn(self):
        # TODO: Check if user actually got logged in
        return True


class DeilduProvider(generic.TorrentProvider):

    def __init__(self):

        generic.TorrentProvider.__init__(self, "Deildu")

        self.supportsBacklog = True
        self.cache = DeilduCache(self)
        self.url = 'http://deildu.net/'

        self.searchurl = self.url + 'browse.php?cat=0&search=%s&sort=seeders&type=desc'
        self.re_title_url = '<tr>.*?browse\.php.*?details\.php\?id=(?P<id>\d+).+?<b>(?P<title>.*?)</b>.+?class=\"index\" href=\"(?P<url>.*?)".+?sinnum.+?align=\"right\">(?P<seeders>.*?)</td>.*?align=\"right\">(?P<leechers>.*?)</td>.*?</tr>'

    def isEnabled(self):
        return sickbeard.DEILDU

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

        results = []
        items = {'Season': [], 'Episode': []}
        dlh = DeilduLoginHandler()

# http://deildu.net/bot.php?search=gadget+show&cat=8
# 1 'http://deildu.net/bot.php?cat=8&search=%s&sort=seeders&type=desc'
# 2 'http://deildu.net/browse.php?cat=0&search=%s&sort=seeders&type=desc'
# setja tvo search url, possible ?
        self.deildu_urls_1 = self.url + '/browse.php?cat=0&search=%s&sort=seeders&type=desc'
        self.deildu_urls_2 = self.url + '/bot.php?cat=8&search=%s&sort=seeders&type=desc'
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                search_string = search_string.replace('.', ' ')

#                search_string = search_string.replace('Á','A')
#                search_string = search_string.replace('á','a')
#                search_string = search_string.replace('í','i')
#                search_string = search_string.replace('ð','d')

                search_string = search_string.encode('cp1252', 'ignore')

                searchURL = self.searchurl % (urllib.quote(search_string))
                searchURL_2 = self.deildu_urls_2 % (urllib.quote(search_string))
                logger.log(u"Search url: " + searchURL, logger.DEBUG)
                logger.log(u"Search string: " + urllib.quote(search_string), logger.DEBUG)
                logger.log(u"Search url: " + searchURL_2, logger.DEBUG)
                logger.log(u"Search string: " + urllib.quote(search_string), logger.DEBUG)
                # make sure we've got a cookie ready to use deildu.net
                if not dlh.loggedIn():
                    logger.log("User or pass for Deildu.net not correct", logger.ERROR)
                    return []
                logger.log(u"deildu.py Got cookie from Deildu", logger.DEBUG)
                # get the browse url with the cookiejar provided to get in
                data = self.getURL(searchURL, [], dlh.cj)
                if 'login' in data:
                    logger.log("Login handler failed, login form or nothing returned data1", logger.ERROR)
#                    continue
#                    return []
                # a crude way of checking if deildu returned no results
                if not data:
                    logger.log("Deildu reported that no torrent was found  data1", logger.MESSAGE)
#                    continue
#                    return []
                #Extracting torrent information from data returned by searchURL
                try:
                    match = re.compile(self.re_title_url, re.DOTALL).finditer(urllib.unquote(data))
                except:
                    logger.log("deildu.py: vesen i regex", logger.DEBUG)
#                if match:
#                    templen = list(match)
#                    logger.log("deildu.py: size of match is : " + str(len(templen)), logger.DEBUG)
#                match = match.decode('cp1252').encode('utf8')
                for torrent in match:
                    title = torrent.group('title').replace('_', '.').decode('cp1252')
                    logger.log(u"deildu.py torrent match loop data1: " + str(title), logger.DEBUG)
                    url = torrent.group('url').decode('cp1252')
                    id = int(torrent.group('id'))
 #                   seeders = int(re.sub('<[^<]+?>', '', torrent.group('seeders')))
 # why not regex only digits ?
                    seeders = int(re.sub('\D', '', torrent.group('seeders')))
                    leechers = int(re.sub('\D', '', torrent.group('leechers')))
                    #Filter unseeded torrent
                    if seeders == 0:
                        continue
                    if not show_name_helpers.filterBadReleases(title):
                        continue
                    if not title:
                        continue
                    item = title, self.url + url, id, seeders, leechers
                    items[mode].append(item)
                logger.log("deildu.py: starting data2", logger.MESSAGE)
                data_2 = self.getURL(searchURL_2, [], dlh.cj)
                logger.log("deildu.py: data2 starting", logger.MESSAGE)
                if 'login' in data_2:
                    logger.log("Login handler failed, login form or nothing returned data2", logger.ERROR)
#                    continue
                # a crude way of checking if deildu returned no results
                if 'Ekkert fannst!' in data_2:
                    logger.log("Deildu reported that no torrent was found data2", logger.MESSAGE)
#                    continue
                #Extracting torrent information from data returned by searchURL
                try:
                    match = re.compile(self.re_title_url, re.DOTALL).finditer(urllib.unquote(data_2))
                except:
                    logger.log("deildu.py: vesen i regex, part 2", logger.DEBUG)
                for torrent in match:
                    title = torrent.group('title').replace('_', '.').decode('cp1252')
                    logger.log(u"deildu.py torrent match loop data2 : " + str(title), logger.DEBUG)
                    url = torrent.group('url').decode('cp1252')
                    id = int(torrent.group('id'))
                    seeders = int(re.sub('\D', '', torrent.group('seeders')))
                    leechers = int(re.sub('\D', '', torrent.group('leechers')))
                    #Filter unseeded torrent
                    if seeders == 0:
                        continue
                    if not show_name_helpers.filterBadReleases(title):
                        continue
                    if not title:
                        continue
                    item = title, self.url + url, id, seeders, leechers
                    items[mode].append(item)
            #For each search mode sort all the items by seeders
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

        logger.log(u"Making sure we have a cookie for Deildu", logger.DEBUG)

        dlh = DeilduLoginHandler()

        logger.log(u"Downloading a result from " + self.name + " at " + result.url)

        data = self.getURL(result.url, [], dlh.cj)

        if data is None:
            return False

        saveDir = sickbeard.TORRENT_DIR
        writeMode = 'wb'

        # use the result name as the filename
        fileName = ek.ek(os.path.join, saveDir, helpers.sanitizeFileName(result.name) + '.' + self.providerType)

        logger.log(u"Saving to " + fileName, logger.DEBUG)

        try:
            fileOut = open(fileName, writeMode)
            fileOut.write(data)
            fileOut.close()
            helpers.chmodAsParent(fileName)
        except IOError, e:
            logger.log("Unable to save the file: " + ex(e), logger.ERROR)
            return False

        # as long as it's a valid download then consider it a successful snatch
        return self._verify_download(fileName)

    def getURL(self, url, headers=None, cj=None):

        if not headers:
            headers = []

        result = None

        try:
#            result = helpers.getURL(url, headers)
            result = helpers.getURL(url, [], cj)
        except (urllib2.HTTPError, IOError), e:
            logger.log(u"Error loading " + self.name + " URL: " + str(sys.exc_info()) + " - " + ex(e), logger.ERROR)
            return None
        return result


class DeilduCache(tvcache.TVCache):

    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll Deildu every 10 minutes max
        self.minTime = 10

    def updateCache(self):

        re_title_url = self.provider.re_title_url

        if not self.shouldUpdate():
            return

        data = self._getData()

        # as long as the http request worked we count this as an update
        if data:
            self.setLastUpdate()
        else:
            return []

        # now that we've loaded the current Deildu data lets delete the old cache
        logger.log(u"Clearing " + self.provider.name + " cache and updating with new information")
        self._clearCache()

        match = re.compile(re_title_url, re.DOTALL).finditer(urllib.unquote(data))
        if not match:
            logger.log(u"The Data returned from Deildu is incomplete, this result is unusable", logger.ERROR)
            return []

        for torrent in match:

            title = torrent.group('title').replace('_', '.')  # Do not know why but SickBeard skip release with '_' in name
            url = torrent.group('url')

            item = (title, url)

            self._parseItem(item)

    def _getData(self):

# url for the last 50 tv-show
        url = self.provider.url + 'bot.php?c12=1&c8=1&incldead=0'
        logger.log(u"Deildu cache update URL: " + url, logger.DEBUG)

        data = self.provider.getURL(url)
        return data

    def _parseItem(self, item):

        (title, url) = item

        if not title or not url:
            return

        logger.log(u"Adding item to cache: " + title, logger.DEBUG)

        self._addCacheEntry(title, url)

provider = DeilduProvider()
