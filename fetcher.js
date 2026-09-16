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

export function cleanAccents(text) {
  if (!text) return '';
  return text.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLowerCase().trim();
}

export function normalizeTeam(name) {
  if (!name) return '';
  let n = cleanAccents(name);
  const prefixes = ['club atletico ', 'atletico ', 'ca ', 'cd ', 'cf ', 'fc ', 'ad ', 'sc ', 'sp ', 'clube de regatas '];
  for (const prefix of prefixes) {
    if (n.startsWith(prefix)) {
      n = n.slice(prefix.length);
      break;
    }
  }
  return n.replace(/[^a-z0-9]/g, '');
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
    return { badgeClass: 'badge-argentina', cleanLeague: 'Liga Profesional Clausura', cleanCountry: 'Argentina' };
  }
  if (['bra', 'brazil', 'brasil'].some(k => cc.includes(k)) || ['brasileirão', 'brasileiro', 'série a', 'serie a'].some(k => full.includes(k))) {
    return { badgeClass: 'badge-brazil', cleanLeague: 'Série A', cleanCountry: 'Brazil' };
  }

  return { badgeClass: 'badge-default', cleanLeague: leagueName, cleanCountry: countryName || 'LATAM' };
}

export function isTargetMatch(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (lg.includes('copa paulista') || full.includes('copa paulista')) return false;
  return ['libertadores', 'sudamericana', 'copa do brasil', 'copa argentina', 'argentina', 'brasil', 'brazil', 'serie a', 'série a'].some(k => full.includes(k));
}

export function getChannelsForMatch(leagueName, countryName) {
  const lg = (leagueName || '').toLowerCase();
  const cc = (countryName || '').toLowerCase();
  const full = `${cc} ${lg}`;

  if (full.includes('libertadores')) {
    return ['Paramount+', 'ESPN', 'Star+', 'Globo'];
  } else if (full.includes('sudamericana')) {
    return ['ESPN 3', 'Star+', 'DSports', 'Paramount+'];
  } else if (full.includes('argentina') || cc.includes('arg') || lg.includes('liga profesional') || lg.includes('copa argentina')) {
    return ['ESPN Premium', 'TNT Sports', 'TyC Sports', 'Star+'];
  } else if (full.includes('brazil') || full.includes('brasil') || cc.includes('bra') || lg.includes('série a') || lg.includes('serie a') || lg.includes('copa do brasil')) {
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
    let minDisp = liveTime ? liveTime.trim() : 'LIVE';
    let text = minDisp !== 'LIVE' ? `LIVE 🔴 ${minDisp}` : 'LIVE 🔴';
    if (scoreStr) text += ` (${scoreStr})`;
    return { text, statusClass: 'status-live' };
  }
  if (!matchDt) return { text: 'SCHEDULED', statusClass: 'status-scheduled' };

  const now = new Date();
  const diffSec = (now.getTime() - matchDt.getTime()) / 1000;

  if (diffSec > 7200) {
    const text = scoreStr ? `FINISHED (${scoreStr})` : 'FINISHED';
    return { text, statusClass: 'status-finished' };
  } else if (diffSec >= 0) {
    const minElapsed = Math.max(1, Math.floor(diffSec / 60));
    const minDisp = minElapsed <= 45 ? `${minElapsed}'` : (minElapsed <= 60 ? 'HT' : `${minElapsed - 15}'`);
    let text = `LIVE 🔴 ${minDisp}`;
    if (scoreStr) text += ` (${scoreStr})`;
    return { text, statusClass: 'status-live' };
  } else if (-diffSec <= 3600) {
    const mins = Math.max(1, Math.floor((-diffSec) / 60));
    return { text: `SOON (${mins}m)`, statusClass: 'status-soon' };
  } else {
    return { text: 'SCHEDULED', statusClass: 'status-scheduled' };
  }
}

export function buildHdBannerUrl(homeName, awayName, existingBanner = '') {
  if (existingBanner && existingBanner.includes('aspijik07.github.io/football-bot/banners/')) {
    return existingBanner;
  }
  const h = normalizeTeam(homeName);
  const a = normalizeTeam(awayName);
  return `https://aspijik07.github.io/football-bot/banners/${h}_${a}.jpg`;
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
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
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
        const isBrazil = (cleanCountry === 'Brazil');

        for (const m of (lg.matches || [])) {
          const st = m.status || {};
          const utcTime = st.utcTime;
          const matchDt = utcTime ? new Date(utcTime) : null;

          const mTime = matchDt
            ? matchDt.toLocaleTimeString('en-GB', { timeZone: 'Africa/Casablanca', hour: '2-digit', minute: '2-digit', hour12: false })
            : '23:00';
          const localTz = isBrazil ? 'America/Sao_Paulo' : 'America/Argentina/Buenos_Aires';
          const localTime = matchDt
            ? matchDt.toLocaleTimeString('en-GB', { timeZone: localTz, hour: '2-digit', minute: '2-digit', hour12: false })
            : '19:00';

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
          const bannerUrl = buildHdBannerUrl(homeName, awayName);

          matches.push({
            day: dayLabel,
            day_label: dayLabel === 'tomorrow' ? 'Tomorrow' : 'Today',
            match_date: `${yyyy}-${mm}-${dd}`,
            league: cleanLeague,
            country: cleanCountry,
            badge_class: badgeClass,
            home_team: homeName,
            away_team: awayName,
            home_logo: homeLogo,
            away_logo: awayLogo,
            local_time: localTime,
            morocco_time: mTime,
            status: statusText,
            status_text: statusText,
            status_class: statusClass,
            is_live: statusText.includes('LIVE'),
            channels: getChannelsForMatch(cleanLeague, cleanCountry),
            banner_url: bannerUrl,
            banner_title: `${homeName} vs ${awayName}`,
            banner_source_site: 'Auto Studio HD',
            has_scraped_banner: true,
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

export function loadCachedMatches() {
  const matchesPath = path.join(__dirname, 'matches.json');
  if (fs.existsSync(matchesPath)) {
    try {
      const raw = fs.readFileSync(matchesPath, 'utf8');
      const parsed = JSON.parse(raw);
      const list = parsed.matches || [...(parsed.today || []), ...(parsed.tomorrow || [])];
      return list.map(item => {
        const rawDay = String(item.day || item.day_label || 'Today').toLowerCase();
        const day = (rawDay === 'tomorrow' || rawDay === 'amanha' || rawDay === 'mañana') ? 'tomorrow' : 'today';
        const stText = (item.status_text || item.status || 'SCHEDULED');
        const cleanStText = (stText.toUpperCase() === 'UNDEFINED' || !stText) ? 'SCHEDULED' : stText;
        const stClass = item.status_class || (cleanStText.includes('LIVE') ? 'status-live' : (cleanStText.includes('SOON') ? 'status-soon' : (cleanStText.includes('FINISHED') ? 'status-finished' : 'status-scheduled')));

        const bannerUrl = buildHdBannerUrl(item.home_team, item.away_team, item.banner_url);

        return {
          day: day,
          day_label: day === 'tomorrow' ? 'Tomorrow' : 'Today',
          match_date: item.match_date,
          league: item.league || 'Liga Profesional',
          country: item.country || 'Argentina',
          badge_class: item.badge_class || getLeagueBadgeInfo(item.league, item.country).badgeClass,
          home_team: item.home_team || '',
          away_team: item.away_team || '',
          home_logo: item.home_logo || '',
          away_logo: item.away_logo || '',
          local_time: item.local_time || '19:00',
          morocco_time: item.morocco_time || '23:00',
          status: cleanStText,
          status_text: cleanStText,
          status_class: stClass,
          is_live: cleanStText.includes('LIVE'),
          channels: (item.channels && item.channels.length > 0) ? item.channels : (item.all_unique_channels || ['TNT Sports', 'ESPN Premium']),
          banner_url: bannerUrl,
          banner_title: item.banner_title || `${item.home_team} vs ${item.away_team}`,
          banner_source_site: 'Auto Studio HD',
          has_scraped_banner: true,
          source: 'cache'
        };
      });
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

    const fmMatches = await fetchFotmobMatches(targetDate, dayLabel);
    combinedMatches.push(...fmMatches);
  }

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
    return loadCachedMatches();
  }

  return uniqueMatches;
}
