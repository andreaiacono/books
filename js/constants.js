export const SUBJECTS = [
  'Art','Biography','Biology','Crafts','Crime','Curiosities','Diary','Drama',
  'Economics','Education','Fiction','Food','History','Geography','Humor','Language',
  'Math','Medicine','Misc','Music','Mythology','Nature','Neuroscience','Philosophy',
  'Photography','Physics','Poetry','Politics','Psychology','Religion','Reportage',
  'Science','Science Fiction','Sociology','Sport','Technology','Travel','War'
];

// Keyword → subject mapping: raw subject words from APIs → our category
export const SUBJECT_KEYWORDS = {
  'Art':             ['art','painting','sculpture','drawing','illustration','design','architecture','museum','gallery'],
  'Biography':       ['biography','autobio','memoir','life of','personal narrative','diary','personal history'],
  'Biology':         ['biology','botany','zoology','ecology','genetics','microbiology','evolution','life science','organism'],
  'Crafts':          ['craft','knitting','sewing','woodwork','pottery','diy','handmade','hobby'],
  'Crime':           ['crime','detective','mystery','thriller','noir','murder','investigation','police','forensic'],
  'Curiosities':     ['curiosities','oddities','weird','strange','unusual','trivia','miscellany','wonders'],
  'Diary':           ['diary','journal','letters','correspondence','personal'],
  'Drama':           ['drama','play','theatre','theater','playwriting','screenplay','script'],
  'Economics':       ['economics','economy','finance','business','trade','market','capitalism','monetary','banking','investment'],
  'Education':       ['education','teaching','pedagogy','learning','school','curriculum','didactic'],
  'Fiction':         ['fiction','novel','short stories','literary','narrative','story','tales'],
  'Food':            ['food','cooking','gastronomy','cuisine','recipe','chef','culinary','nutrition'],
  'History':         ['history','historical','ancient','medieval','modern history','world war','civilization','heritage'],
  'Geography':       ['geography','cartography','map','region','landscape','territory','place'],
  'Humor':           ['humor','humour','comedy','satire','parody','wit','funny','comic'],
  'Language':        ['language','linguistics','grammar','etymology','dictionary','philology','translation','lexicon'],
  'Math':            ['math','mathematics','algebra','geometry','calculus','statistics','probability','number theory'],
  'Medicine':        ['medicine','medical','health','disease','anatomy','physiology','clinical','surgery','pharmacy','psychiatry'],
  'Misc':            ['miscellaneous','general','reference','collection'],
  'Music':           ['music','musicology','composition','jazz','classical','opera','rock','song','instrument'],
  'Mythology':       ['mythology','myth','legend','folklore','fairy tale','epic','fable'],
  'Nature':          ['nature','environment','wildlife','plants','animals','natural world','conservation','outdoor'],
  'Neuroscience':    ['neuroscience','neurology','brain','cognition','neural','consciousness','cognitive science'],
  'Philosophy':      ['philosophy','ethics','metaphysics','epistemology','logic','phenomenology','aesthetics','moral'],
  'Photography':     ['photography','photo','photographic','camera'],
  'Physics':         ['physics','quantum','mechanics','thermodynamics','relativity','electromagnetism','optics','astrophysics'],
  'Poetry':          ['poetry','poem','verse','lyric','haiku','sonnet'],
  'Politics':        ['politics','political','government','democracy','law','diplomacy','international relations','policy','justice'],
  'Psychology':      ['psychology','psychoanalysis','behavior','mental','personality','developmental','social psychology'],
  'Religion':        ['religion','theology','spirituality','bible','quran','buddhism','christianity','islam','faith','sacred'],
  'Reportage':       ['journalism','reportage','report','news','investigative','documentary','nonfiction narrative'],
  'Science':         ['science','scientific','chemistry','biology','physics','astronomy','geology','earth science'],
  'Science Fiction': ['science fiction','sci-fi','sci fi','speculative','dystopia','utopia','cyberpunk','space opera','futuristic'],
  'Sociology':       ['sociology','society','culture','anthropology','social','community','ethnography'],
  'Sport':           ['sport','sports','athletics','football','basketball','tennis','running','cycling','swimming','fitness'],
  'Technology':      ['technology','engineering','computer','software','hardware','programming','internet','artificial intelligence','robotics'],
  'Travel':          ['travel','voyage','journey','exploration','adventure','travelogue','guide','tourism'],
  'War':             ['war','military','battle','conflict','army','navy','air force','soldier','combat','weaponry'],
};

export const LANG_LABELS = {
  it: 'Italian', en: 'English', es: 'Spanish', fr: 'French'
};
