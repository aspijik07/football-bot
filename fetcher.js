import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const MATCH_STOP_WORDS = new Set([
  'club', 'atletico', 'atlético', 'ca', 'cd', 'cf', 'fc', 'sp', 'sc', 'ad',
  'de', 'la', 'del', 'el', 'los', 'las', 'da', 'do', 'dos', 'das', 'e',
  'deportivo', 'deportiva', 'sport', 'social', 'asociacion', 'asociación'
]);

export function normalizeTeam(name) {
  if (!name) return '';
  let n = name.toLowerCase().trim();
  const prefixes = ['club atlético ', 'club atletico ', 'ca ', 'cd ', 'cf ', 'fc ', 'ad ', 'sc '];
  for (const prefix of prefixes) {
    if (n.startsWith(prefix)) {
      n = n.slice(prefix.length);
      break;
    }
  }
  return n.replace(/[^a-z0-9]/gi, '');
}

export function cleanNameForMatching(text) {
  if (!text) return '';
  return text
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

export function extractTeamTokens(teamName) {
  const clean = cleanNameForMatching(teamName);
  const words = clean.split(' ');
  let tokens = words.filter(w => !MATCH_STOP_WORDS.has(w) && w.length >= 3);
  if (!tokens.length) {
    tokens = words.filter(w => w.length >= 3);
  }
  return { tokens, clean };
}

export function getLeagueBadgeInfo(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (lg.includes('libertadores') || full.includes('libertadores')) {
    return { badgeClass: 'badge-libertadores', cleanLeague: 'Copa Libertadores', cleanCountry: 'South America' };
  }
  if (lg.includes('sudamericana') || full.includes('sudamericana')) {
    return { badgeClass: 'badge-sudamericana', cleanLeague: 'Copa Sudamericana', cleanCountry: 'South America' };
  }
  if (lg.includes('copa do brasil') || lg.includes('copa brasil') || full.includes('copa do brasil')) {
    return { badgeClass: 'badge-brazil', cleanLeague: 'Copa do Brasil', cleanCountry: 'Brazil' };
  }
  if (lg.includes('copa argentina') || full.includes('copa argentina')) {
    return { badgeClass: 'badge-argentina', cleanLeague: 'Copa Argentina', cleanCountry: 'Argentina' };
  }
  if (['argentina', 'arg', 'clausura', 'apertura', 'liga profesional'].some(k => full.includes(k))) {
    return { badgeClass: 'badge-argentina', cleanLeague: leagueName, cleanCountry: 'Argentina' };
  }
  if (
    ['bra', 'brazil', 'brasil'].some(k => cc.includes(k)) ||
    [
      'brazil', 'brasil', 'bra', 'brasileiro', 'brasileirão', 'paulista',
      'paulistão', 'série a', 'serie a', 'série b', 'serie b',
      'copa do brasil', 'copa paulista', 'carioca', 'gaúcho', 'gaucho', 'mineiro'
    ].some(k => full.includes(k))
  ) {
    return { badgeClass: 'badge-brazil', cleanLeague: leagueName, cleanCountry: 'Brazil' };
  }

  return { badgeClass: 'badge-default', cleanLeague: leagueName, cleanCountry: countryName || 'LATAM' };
}

export function isTargetMatch(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (lg.includes('libertadores') || full.includes('libertadores')) return true;
  if (lg.includes('sudamericana') || full.includes('sudamericana')) return true;
  if (lg.includes('copa argentina') || full.includes('copa argentina')) return true;
  if (lg.includes('copa do brasil') || lg.includes('copa brasil') || full.includes('copa do brasil')) return true;

  if (cc.includes('arg') || full.includes('argentina')) {
    if (['liga profesional', 'copa argentina', 'clausura', 'apertura', 'supercopa', 'trofeo de campeones', 'copa de la liga'].some(k => lg.includes(k))) {
      return true;
    }
  }

  if (cc.includes('bra') || full.includes('brazil') || full.includes('brasil')) {
    if (['série a', 'serie a', 'brasileir', 'paulistão', 'copa do brasil', 'carioca'].some(k => lg.includes(k))) {
      return true;
    }
  }

  return false;
}

export function getChannelsForMatch(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (full.includes('libertadores')) {
    return ['ESPN', 'Fox Sports', 'Star+', 'Globo'];
  } else if (full.includes('sudamericana')) {
    return ['ESPN 3', 'Star+', 'DSports', 'Paramount+'];
  } else if (full.includes('argentina') || cc.includes('arg') || lg.includes('liga profesional') || lg.includes('copa argentina')) {
    return ['ESPN Premium', 'TNT Sports', 'TyC Sports', 'Star+'];
  } else if (full.includes('brazil') || full.includes('brasil') || cc.includes('bra') || lg.includes('série a') || lg.includes('serie a') || lg.includes('paulista') || lg.includes('copa do brasil') || lg.includes('copa paulista')) {
    return ['Premiere', 'Globo', 'SporTV', 'CazéTV'];
  }
  return ['TNT Sports', 'ESPN Premium'];
}

export function calculateStatus(matchDt, started = false, finished = false, cancelled = false, scoreStr = null, liveTime = null) {
  if (cancelled) return { text: 'CANCELLED', statusClass: 'status-cancelled' };
  if (finished) {
    const text = scoreStr ? `FINISHED (${scoreStr})` : 'FINISHED';
    return { text, statusClass: 'status-finished' };
  }
  if (started) {
    let text = 'LIVE 🔴';
    if (liveTime) text = `LIVE 🔴 ${liveTime}`;
    else if (scoreStr) text = `LIVE 🔴 (${scoreStr})`;
    return { text, statusClass: 'status-live' };
  }
  if (!matchDt) return { text: 'SCHEDULED', statusClass: 'status-scheduled' };

  const now = new Date();
  const diffMs = matchDt.getTime() - now.getTime();
  if (diffMs <= 0) {
    const text = scoreStr ? `LIVE 🔴 (${scoreStr})` : 'LIVE 🔴';
    return { text, statusClass: 'status-live' };
  } else if (diffMs <= 3600 * 1000) {
    const mins = Math.max(1, Math.floor(diffMs / 60000));
    return { text: `SOON (${mins}m)`, statusClass: 'status-soon' };
  } else {
    return { text: 'SCHEDULED', statusClass: 'status-scheduled' };
  }
}

export function rewriteCdnImageUrl(url) {
  if (!url) return url;
  const bases = [
    'https://www.zerozero.com.ar', 'http://www.zerozero.com.ar',
    'https://zerozero.com.ar', 'http://zerozero.com.ar',
    'https://www.ogol.com.br', 'http://www.ogol.com.br',
    'https://ogol.com.br', 'http://ogol.com.br',
    'https://www.zerozero.pt', 'http://www.zerozero.pt',
    'https://zerozero.pt', 'http://zerozero.pt'
  ];
  for (const b of bases) {
    if (url.startsWith(b)) {
      return 'https://cdn-img.staticzz.com' + url.slice(b.length);
    }
  }
  return url;
}

export async function fetchFotmobMatches(targetDate, dayLabel) {
  const matches = [];
  const yyyy = targetDate.getUTCFullYear();
  const mm = String(targetDate.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(targetDate.getUTCDate()).padStart(2, '0');
  const dateFotmob = `${yyyy}${mm}${dd}`;
  const url = `https://www.fotmob.com/api/data/matches?date=${dateFotmob}`;

  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://www.fotmob.com/'
      },
      signal: AbortSignal.timeout(8000)
    });
    if (!res.ok) return matches;
    const data = await res.json();
    if (!data || !Array.isArray(data.leagues)) return matches;

    for (const lg of data.leagues) {
      const lgName = lg.name || '';
      const lgCcode = lg.ccode || '';

      if (isTargetMatch(lgName, lgCcode)) {
        const { badgeClass, cleanLeague, cleanCountry } = getLeagueBadgeInfo(lgName, lgCcode);

        for (const m of (lg.matches || [])) {
          const st = m.status || {};
          const utcTime = st.utcTime;
          const matchDt = utcTime ? new Date(utcTime) : null;

          const mTime = matchDt
            ? matchDt.toLocaleTimeString('en-GB', { timeZone: 'Africa/Casablanca', hour: '2-digit', minute: '2-digit', hour12: false })
            : 'TBD';
          const localTime = matchDt
            ? matchDt.toLocaleTimeString('en-GB', { timeZone: 'America/Argentina/Buenos_Aires', hour: '2-digit', minute: '2-digit', hour12: false })
            : 'TBD';

          const started = Boolean(st.started);
          const finished = Boolean(st.finished);
          const cancelled = Boolean(st.cancelled);
          const scoreStr = st.scoreStr || null;
          const liveTime = typeof st.liveTime === 'object' && st.liveTime ? st.liveTime.short : null;

          const { text: statusText, statusClass } = calculateStatus(matchDt, started, finished, cancelled, scoreStr, liveTime);

          const home = m.home || {};
          const away = m.away || {};
          const homeName = home.name || 'Home';
          const awayName = away.name || 'Away';
          const homeId = home.id;
          const awayId = away.id;

          const homeLogo = homeId ? `https://images.fotmob.com/image_resources/logo/teamlogo/${homeId}.png` : '';
          const awayLogo = awayId ? `https://images.fotmob.com/image_resources/logo/teamlogo/${awayId}.png` : '';

          matches.push({
            day: dayLabel,
            league: cleanLeague,
            country: cleanCountry,
            badge_class: badgeClass,
            home_team: homeName,
            away_team: awayName,
            home_logo: homeLogo,
            away_logo: awayLogo,
            local_time: localTime,
            morocco_time: mTime,
            status_text: statusText,
            status_class: statusClass,
            channels: getChannelsForMatch(cleanLeague, cleanCountry),
            banner_url: homeLogo,
            source: 'fotmob'
          });
        }
      }
    }
  } catch (err) {
    console.warn('Fotmob fetch notice:', err.message);
  }

  return matches;
}

export async function fetchSofascoreMatches(targetDate, dayLabel) {
  const matches = [];
  const yyyy = targetDate.getUTCFullYear();
  const mm = String(targetDate.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(targetDate.getUTCDate()).padStart(2, '0');
  const dateIso = `${yyyy}-${mm}-${dd}`;
  const url = `https://api.sofascore.com/api/v1/sport/football/scheduled-events/${dateIso}`;

  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Referer': 'https://www.sofascore.com/'
      },
      signal: AbortSignal.timeout(8000)
    });
    if (!res.ok) return matches;
    const data = await res.json();
    if (!data || !Array.isArray(data.events)) return matches;

    for (const ev of data.events) {
      const tournament = ev.tournament || {};
      const tName = tournament.name || '';
      const catName = tournament.category ? tournament.category.name : '';

      if (isTargetMatch(tName, catName)) {
        const { badgeClass, cleanLeague, cleanCountry } = getLeagueBadgeInfo(tName, catName);
        const ts = ev.startTimestamp;
        const matchDt = ts ? new Date(ts * 1000) : null;

        const mTime = matchDt
          ? matchDt.toLocaleTimeString('en-GB', { timeZone: 'Africa/Casablanca', hour: '2-digit', minute: '2-digit', hour12: false })
          : 'TBD';
        const localTime = matchDt
          ? matchDt.toLocaleTimeString('en-GB', { timeZone: 'America/Argentina/Buenos_Aires', hour: '2-digit', minute: '2-digit', hour12: false })
          : 'TBD';

        const stObj = ev.status || {};
        const stType = stObj.type || '';
        const finished = (stType === 'finished');
        const started = (stType === 'inprogress');
        const cancelled = (stType === 'canceled');

        const hScore = ev.homeScore ? ev.homeScore.current : null;
        const aScore = ev.awayScore ? ev.awayScore.current : null;
        const scoreStr = (hScore != null && aScore != null) ? `${hScore} - ${aScore}` : null;

        const { text: statusText, statusClass } = calculateStatus(matchDt, started, finished, cancelled, scoreStr);

        const homeTeam = ev.homeTeam || {};
        const awayTeam = ev.awayTeam || {};
        const homeName = homeTeam.name || 'Home';
        const awayName = awayTeam.name || 'Away';
        const homeId = homeTeam.id;
        const awayId = awayTeam.id;

        const homeLogo = homeId ? `https://api.sofascore.app/api/v1/team/${homeId}/image` : '';
        const awayLogo = awayId ? `https://api.sofascore.app/api/v1/team/${awayId}/image` : '';

        matches.push({
          day: dayLabel,
          league: cleanLeague,
          country: cleanCountry,
          badge_class: badgeClass,
          home_team: homeName,
          away_team: awayName,
          home_logo: homeLogo,
          away_logo: awayLogo,
          local_time: localTime,
          morocco_time: mTime,
          status_text: statusText,
          status_class: statusClass,
          channels: getChannelsForMatch(cleanLeague, cleanCountry),
          banner_url: homeLogo,
          source: 'sofascore'
        });
      }
    }
  } catch (err) {
    console.warn('Sofascore fetch notice:', err.message);
  }

  return matches;
}

export function loadCachedMatches() {
  const matchesPath = path.join(__dirname, 'matches.json');
  if (fs.existsSync(matchesPath)) {
    try {
      const raw = fs.readFileSync(matchesPath, 'utf8');
      const parsed = JSON.parse(raw);
      const list = parsed.matches || [];
      return list.map(item => ({
        day: (item.day_label || 'Today').toLowerCase(),
        league: item.league || 'Liga Profesional',
        country: item.country || 'Argentina',
        badge_class: item.badge_class || getLeagueBadgeInfo(item.league, item.country).badgeClass,
        home_team: item.home_team || '',
        away_team: item.away_team || '',
        home_logo: item.home_logo || '',
        away_logo: item.away_logo || '',
        local_time: item.local_time || '20:00',
        morocco_time: item.morocco_time || '00:00',
        status_text: item.status || 'SCHEDULED',
        status_class: 'status-scheduled',
        channels: item.all_unique_channels || ['TNT Sports', 'ESPN Premium'],
        banner_url: rewriteCdnImageUrl(item.banner_url || item.home_logo || ''),
        banner_title: item.banner_title || `${item.home_team} vs ${item.away_team}`,
        banner_source_site: item.banner_source_site || 'zerozero.com.ar',
        has_scraped_banner: item.has_scraped_banner ?? true,
        source: 'cache'
      }));
    } catch (e) {
      console.warn('Error reading matches.json:', e);
    }
  }
  return [];
}

export async function fetchAllMatches() {
  const now = new Date();
  const combinedMatches = [];

  for (const dayOffset of [0, 1]) {
    const dayLabel = dayOffset === 0 ? 'today' : 'tomorrow';
    const targetDate = new Date(now.getTime() + dayOffset * 86400000);

    const [fmMatches, ssMatches] = await Promise.all([
      fetchFotmobMatches(targetDate, dayLabel),
      fetchSofascoreMatches(targetDate, dayLabel)
    ]);

    combinedMatches.push(...fmMatches, ...ssMatches);
  }

  // Deduplicate matches
  const uniqueMatches = [];
  const seen = new Set();
  for (const m of combinedMatches) {
    const h = normalizeTeam(m.home_team).slice(0, 8);
    const a = normalizeTeam(m.away_team).slice(0, 8);
    const id = `${m.day}_${h}_${a}`;
    if (!seen.has(id)) {
      seen.add(id);
      uniqueMatches.push(m);
    }
  }

  if (uniqueMatches.length === 0) {
    console.log('No live matches found over network or rate limited, falling back to cache');
    return loadCachedMatches();
  }

  // Persist updated matches.json
  try {
    const payload = {
      total_matches: uniqueMatches.length,
      last_updated: new Date().toISOString(),
      matches: uniqueMatches.map(m => ({
        day_label: m.day.charAt(0).toUpperCase() + m.day.slice(1),
        league: m.league,
        country: m.country,
        badge_class: m.badge_class,
        home_team: m.home_team,
        away_team: m.away_team,
        home_logo: m.home_logo,
        away_logo: m.away_logo,
        local_time: m.local_time,
        morocco_time: m.morocco_time,
        status: m.status_text,
        banner_url: m.banner_url,
        banner_title: m.banner_title || `${m.home_team} vs ${m.away_team}`,
        banner_source_site: m.banner_source_site || 'zerozero.com.ar',
        has_scraped_banner: m.has_scraped_banner ?? false,
        all_unique_channels: m.channels
      }))
    };

    const matchesPath = path.join(__dirname, 'matches.json');
    fs.writeFileSync(matchesPath, JSON.stringify(payload, null, 4), 'utf8');

    const distMatchesPath = path.join(__dirname, 'dist', 'matches.json');
    if (fs.existsSync(path.dirname(distMatchesPath))) {
      fs.writeFileSync(distMatchesPath, JSON.stringify(payload, null, 4), 'utf8');
    }
  } catch (err) {
    console.warn('Could not persist updated matches.json:', err);
  }

  return uniqueMatches;
}
