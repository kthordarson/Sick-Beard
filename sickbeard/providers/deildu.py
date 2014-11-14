# -*- coding: utf-8 -*-
# kth edit of iptorrents module from sickbeard
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

import sickbeard
import generic
from sickbeard.common import Quality
from sickbeard import logger
from sickbeard import tvcache
from sickbeard import show_name_helpers
from sickbeard.common import Overview
from sickbeard.exceptions import ex
from lib import requests
from bs4 import BeautifulSoup


class deilduProvider(generic.TorrentProvider):

#    urls = {
#        'base_url': 'http://deildu.net/',
#        'login': 'http://deildu.net/takelogin.php',
#        'detail': 'http://deildu.net/details.php?id=%s',
#        'search': 'http://deildu.net/browse.php?search=%s%s',
#        'base': 'http://deildu.net/',
#    }
    urls = {
        'base_url': 'http://icetracker.org/',
        'login': 'http://icetracker.org/takelogin.php',
        'detail': 'http://icetracker.org/details.php?id=%s',
        'search': 'http://icetracker.org/browse.php?search=%s%s',
        'base': 'http://icetracker.org/',
    }


#        'search': 'http://deildu.net/browse.php?search=%s%s&sort=seeders&type=desc&cat=0',
    def __init__(self):

        generic.TorrentProvider.__init__(self, "deildu")

        self.supportsBacklog = True

        self.cache = deilduCache(self)

        self.url = self.urls['base_url']

        self.session = None

#        self.categories = 73

        self.categorie = ''

    def isEnabled(self):
        return sickbeard.deildu

    def imageName(self):
        return 'iptorrents.png'

    def getQuality(self, item):
        logger.log(u"DEBUG deildu.py someone called getQuality .. sending to nameQuality ..." + str(item))
#        (title, url) = item
        quality = Quality.nameQuality(item)
        return quality

    def _doLogin(self):

        login_params = {'username': sickbeard.deildu_USERNAME,
                        'password': sickbeard.deildu_PASSWORD,
                        'login': 'submit',
                        }

        self.session = requests.Session()
        logger.log(u"DEBUG deildu.py _doLogin running ...")
        try:
            response = self.session.post(self.urls['login'], data=login_params, timeout=30)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError), e:
            logger.log(u'Unable to connect to ' + self.name + ' provider: ' +ex(e), logger.ERROR)
            return False

        if re.search('tries left', response.text) \
        or re.search('<title>IPT</title>', response.text) \
        or response.status_code == 401:
            logger.log(u'Invalid username or password for ' + self.name + ' Check your settings', logger.ERROR)
            return False

        return True

    def _get_season_search_strings(self, show, season=None):

        search_string = {'Episode': []}

        if not show:
            return []

        seasonEp = show.getAllEpisodes(season)

        wantedEp = [x for x in seasonEp if show.getOverview(x.status) in (Overview.WANTED, Overview.QUAL)]

        #If Every episode in Season is a wanted Episode then search for Season first
        if wantedEp == seasonEp and not show.air_by_date:
            search_string = {'Season': [], 'Episode': []}
            for show_name in set(show_name_helpers.allPossibleShowNames(show)):
                ep_string = show_name +' S%02d' % int(season) #1) ShowName SXX
                search_string['Season'].append(ep_string)

        #Building the search string with the episodes we need
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
                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ str(ep_obj.airdate)
                search_string['Episode'].append(ep_string)
        else:
            for show_name in set(show_name_helpers.allPossibleShowNames(ep_obj.show)):
                ep_string = show_name_helpers.sanitizeSceneName(show_name) +' '+ \
                sickbeard.config.naming_ep_type[2] % {'seasonnumber': ep_obj.season, 'episodenumber': ep_obj.episode}

                search_string['Episode'].append(ep_string)

        return [search_string]

    def _doSearch(self, search_params, show=None):

        results = []
        items = {'Season': [], 'Episode': []}

        if not self._doLogin():
            return

#        freeleech = '&free=on' if sickbeard.deildu_FREELEECH else ''
        logger.log(u"DEBUG deildu.py _doSearch running...")
        for mode in search_params.keys():
            for search_string in search_params[mode]:
                oldstring = search_string
                search_string = search_string.replace('.', '+')
                search_string = search_string.replace(' ', '+')

                logger.log(u"DEBUG deildu.py _doSearch .. " + str(self.urls['search']) + " " + str(self.categorie) + " " + str(search_string))
                searchURL = self.urls['search'] % (search_string, "&sort=seeders&type=desc&cat=0")

                logger.log(u"Search string: " + searchURL)
                search_string = oldstring
                data = self.getURL(searchURL)
                if not data:
                    return []
                html = data.decode('cp1252')
                html = BeautifulSoup(data)

                try:
                    if html.find(text='Nothing found!'):
                        logger.log(u"No results found for: " + search_string + "(" + searchURL + ")")
                        return []

                    result_table = html.find('table', attrs = {'class' : 'torrentlist'})

                    if not result_table:
                        logger.log(u"No results found for: " + search_string + "(" + searchURL + ")")
                        return []

                    entries = result_table.find_all('tr')

                    for result in entries[1:]:
                        torrent = result.find_all('td')[1].find('a').find('b').string
                        torrent_name = torrent.string
                        torrent_detail_url = self.urls['base_url'] + (result.find_all('td')[3].find('a'))['href']
                        torrent_download_url = self.urls['base_url'] + (result.find_all('td')[2].find('a'))['href']
                        try:
                            torrent_seeders = int((result.find_all('td')[8].find('b').string))
                        except:
                            torrent_seeders = 0
#                        torrent = result.find_all('td').find('a')
#                        torrent_id = int(torrent['href'].replace('/details.php?id=', ''))
#                        torrent_name = torrent.string
#                        torrent_download_url = self.urls['download'] % (torrent_id, torrent_name.replace(' ', '.'))
#                        torrent_details_url = self.urls['detail'] % (torrent_id)
#                        torrent_seeders = int(result.find('td', attrs = {'class' : 'ac t_seeders'}).string)
#                        torrent_leechers = int(result.find('td', attrs = {'class' : 'ac t_leechers'}).string)

                        #Filter unseeded torrent
                        if torrent_seeders == 0 or not torrent_name \
                        or not show_name_helpers.filterBadReleases(torrent_name):
                            continue

                        item = torrent, torrent_download_url
#                        item = torrent_name, torrent_download_url, torrent_id, torrent_seeders, torrent_leechers
                        logger.log(u"DEBUG deildu.py Found result: " + torrent_name + " url " + searchURL)
                        items[mode].append(item)
                        logger.log(u"DEBUG deildu.py appended to items....")

                except Exception, e:
                    logger.log(u"DEBUG deildu.py Failed to parsing " + self.name + " page url: " + searchURL + " " + ex(e))

            #For each search mode sort all the items by seeders
#            items[mode].sort(key=lambda tup: tup[3], reverse=True)

            results += items[mode]
            logger.log(u"DEBUG deildu.py results to items mode ... ")

        return results

    def _get_title_and_url(self, item):

        title, url = item
        logger.log(u"DEBUG deildu.py _get_title_and_url running we got title: " + title + " url " + url)
        if url:
            url = str(url).replace('&amp;','&')
            logger.log(u"DEBUG deildu.py now url got changed to: " + url )

        return (title, url)

    def getURL(self, url, headers=None):
        logger.log(u"DEBUG deildu.py _getURL running...")
        if not self.session:
            self._doLogin()

        if not headers:
            headers = []

        try:
            response = self.session.get(url)
        except (requests.exceptions.ConnectionError, requests.exceptions.HTTPError), e:
            logger.log(u"Error loading "+self.name+" URL: " + ex(e), logger.ERROR)
            return None

        return response.content

class deilduCache(tvcache.TVCache):

    def __init__(self, provider):

        tvcache.TVCache.__init__(self, provider)

        # only poll deildu every 20 minutes max
        self.minTime = 20

    def _getData(self):

#        url = self.provider.urls['search'] % (self.provider.categories, "", "")
        url = self.provider.urls['search'] % ('', '')

        logger.log(u"deildu cache update URL: "+ url)

        data = self.provider.getURL(url)

        return data

    def _parseItem(self, item):

        (title, url) = item

        if not title or not url:
            return

        logger.log(u"Adding item to cache: "+title)

        self._addCacheEntry(title, url)

provider = deilduProvider()
