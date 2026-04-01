-- Seed data for DURC dashboard demo

-- Paper 1: Critical - H5N1 gain-of-function
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.15.001',
  'Enhanced aerosol transmissibility of recombinant H5N1 influenza via directed evolution in ferrets',
  '[{"name": "Chen Wei"}, {"name": "Sarah Mitchell"}, {"name": "Raj Patel"}, {"name": "Yuki Tanaka"}]'::jsonb,
  'Chen Wei', 'Wuhan Institute of Virology',
  'We report the generation of airborne-transmissible H5N1 variants through serial passage in ferrets combined with targeted mutagenesis of the hemagglutinin receptor binding domain. Three amino acid substitutions were sufficient to confer respiratory droplet transmission between co-housed ferrets.',
  'biorxiv', '2026-03-15', 'Microbiology', 1, 'methods_analysed', 'critical', 16, 'escalate', 'unreviewed',
  '{"summary": "Direct gain-of-function on H5N1 with demonstrated airborne transmission in ferrets. Extremely high dual-use concern.", "dimensions": {"pathogen_enhancement": {"score": 3, "justification": "Direct enhancement of H5N1 transmissibility"}, "synthesis_barrier_lowering": {"score": 3, "justification": "Detailed protocol for generating airborne-transmissible variants"}, "select_agent_relevance": {"score": 3, "justification": "H5N1 is a Tier 1 select agent"}, "novel_technique": {"score": 2, "justification": "Combines directed evolution with targeted mutagenesis"}, "information_hazard": {"score": 3, "justification": "Specific mutations and protocol provided"}, "defensive_framing": {"score": 2, "justification": "Minimal discussion of dual-use implications"}}, "aggregate_score": 16}'::jsonb,
  now(), now()
);

-- Paper 2: Critical - 1918 flu reconstruction
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.14.002',
  'Simplified reverse genetics system for reconstructing 1918 influenza from synthetic DNA fragments',
  '[{"name": "James Rodriguez"}, {"name": "Anna Kowalski"}]'::jsonb,
  'James Rodriguez', 'University of Wisconsin-Madison',
  'We describe a streamlined 4-plasmid reverse genetics system that enables reconstruction of the 1918 H1N1 influenza virus from commercially available synthetic DNA. The system reduces the technical barrier compared to the original 8-plasmid approach.',
  'biorxiv', '2026-03-14', 'Virology', 1, 'methods_analysed', 'critical', 15, 'escalate', 'under_review',
  '{"summary": "Dramatically lowers barrier to reconstructing 1918 pandemic influenza.", "dimensions": {"pathogen_enhancement": {"score": 1, "justification": "Reconstruction rather than enhancement"}, "synthesis_barrier_lowering": {"score": 3, "justification": "Explicitly simplifies reconstruction"}, "select_agent_relevance": {"score": 3, "justification": "1918 H1N1 is a Tier 1 select agent"}, "novel_technique": {"score": 3, "justification": "Novel simplified reverse genetics"}, "information_hazard": {"score": 3, "justification": "Complete protocol provided"}, "defensive_framing": {"score": 2, "justification": "Brief biosafety section"}}, "aggregate_score": 15}'::jsonb,
  now(), now()
);

-- Paper 3: High - AI-designed neurotoxin
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.12.003',
  'De novo design of a novel botulinum-like neurotoxin using AlphaFold3 and directed evolution',
  '[{"name": "Marcus Chen"}, {"name": "Elena Voronova"}, {"name": "David Park"}]'::jsonb,
  'Marcus Chen', 'MIT Department of Biological Engineering',
  'We demonstrate that computational protein design guided by AlphaFold3 structure prediction, combined with yeast surface display directed evolution, can generate novel neurotoxins with botulinum-like activity at sub-nanomolar potency.',
  'medrxiv', '2026-03-12', 'Synthetic Biology', 1, 'methods_analysed', 'high', 12, 'review', 'unreviewed',
  '{"summary": "AI-guided design of novel neurotoxin with botulinum-like potency.", "dimensions": {"pathogen_enhancement": {"score": 1, "justification": "Toxin design not pathogen enhancement"}, "synthesis_barrier_lowering": {"score": 2, "justification": "AI pipeline could accelerate toxin discovery"}, "select_agent_relevance": {"score": 2, "justification": "Botulinum toxin is a select agent"}, "novel_technique": {"score": 3, "justification": "First AI-designed neurotoxins with in vivo potency"}, "information_hazard": {"score": 2, "justification": "Sequences not fully disclosed"}, "defensive_framing": {"score": 2, "justification": "Brief ethics discussion"}}, "aggregate_score": 12}'::jsonb,
  now() - interval '3 days', now() - interval '3 days'
);

-- Paper 4: High - Gene drive field trial
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.10.004',
  'CRISPR-based gene drive for suppression of Anopheles gambiae populations: field trial results from Burkina Faso',
  '[{"name": "Abdoulaye Diabate"}, {"name": "Ruth Mueller"}, {"name": "Kwame Asante"}]'::jsonb,
  'Abdoulaye Diabate', 'Institut de Recherche en Sciences de la Sante',
  'We report results from the first open-field release of a CRISPR-Cas9 gene drive targeting doublesex in Anopheles gambiae. Over 18 months, the drive allele spread through the target population, reducing female fertility by 78%.',
  'biorxiv', '2026-03-10', 'Ecology', 1, 'methods_analysed', 'high', 10, 'review', 'unreviewed',
  '{"summary": "First field deployment of gene drive in wild mosquito populations.", "dimensions": {"pathogen_enhancement": {"score": 0, "justification": "No pathogen work"}, "synthesis_barrier_lowering": {"score": 1, "justification": "Gene drive protocols well-established"}, "select_agent_relevance": {"score": 0, "justification": "Mosquitoes not select agents"}, "novel_technique": {"score": 3, "justification": "First open-field gene drive release"}, "information_hazard": {"score": 2, "justification": "Detailed drive construct and release protocol"}, "defensive_framing": {"score": 1, "justification": "Extensive monitoring but limited dual-use discussion"}}, "aggregate_score": 10}'::jsonb,
  now() - interval '5 days', now() - interval '5 days'
);

-- Paper 5: Medium - ML immune evasion prediction
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.08.005',
  'Machine learning prediction of immune evasion mutations in SARS-CoV-2 spike protein',
  '[{"name": "Lisa Chang"}, {"name": "Omar Hassan"}, {"name": "Maria Santos"}]'::jsonb,
  'Lisa Chang', 'Stanford University School of Medicine',
  'We present a deep learning model trained on viral fitness landscapes that predicts which spike protein mutations are most likely to evade current monoclonal antibody therapies. Our model predicted 8 of 10 mutations found in recently emerged variants.',
  'medrxiv', '2026-03-08', 'Computational Biology', 1, 'methods_analysed', 'medium', 8, 'monitor', 'unreviewed',
  '{"summary": "ML model predicting immune evasion mutations. Dual-use concern for guiding pathogen evolution.", "dimensions": {"pathogen_enhancement": {"score": 2, "justification": "Could guide directed immune evasion"}, "synthesis_barrier_lowering": {"score": 1, "justification": "Predictions still require wet lab validation"}, "select_agent_relevance": {"score": 1, "justification": "SARS-CoV-2 not a select agent"}, "novel_technique": {"score": 2, "justification": "Novel predictive model"}, "information_hazard": {"score": 1, "justification": "Model weights not released"}, "defensive_framing": {"score": 1, "justification": "Good responsible AI discussion"}}, "aggregate_score": 8}'::jsonb,
  now() - interval '7 days', now() - interval '7 days'
);

-- Paper 6: Medium - Antiviral resistance
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.07.006',
  'Broad-spectrum antiviral resistance conferred by a single RNA-dependent RNA polymerase mutation in enteroviruses',
  '[{"name": "Thomas Berg"}, {"name": "Priya Sharma"}]'::jsonb,
  'Thomas Berg', 'Karolinska Institute',
  'We identify a single point mutation in the enterovirus RdRp that confers resistance to all currently approved antivirals targeting this enzyme. The mutation maintains viral fitness and is readily selected in cell culture.',
  'europepmc', '2026-03-07', 'Virology', 1, 'methods_analysed', 'medium', 7, 'monitor', 'unreviewed',
  '{"summary": "Single mutation conferring pan-antiviral resistance. Moderate dual-use concern.", "dimensions": {"pathogen_enhancement": {"score": 2, "justification": "Drug resistance enhancement"}, "synthesis_barrier_lowering": {"score": 1, "justification": "Standard virology methods"}, "select_agent_relevance": {"score": 1, "justification": "Most enteroviruses not select agents"}, "novel_technique": {"score": 1, "justification": "Standard resistance selection"}, "information_hazard": {"score": 1, "justification": "Single mutation easy to reproduce"}, "defensive_framing": {"score": 1, "justification": "Discusses drug development implications"}}, "aggregate_score": 7}'::jsonb,
  now() - interval '10 days', now() - interval '10 days'
);

-- Paper 7: Medium - Microfluidic virus production
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.05.007',
  'Microfluidic platform for rapid benchtop production of recombinant viral particles',
  '[{"name": "Kevin O Brien"}, {"name": "Aisha Mohammed"}, {"name": "Jun Li"}, {"name": "Sophie Dubois"}]'::jsonb,
  'Kevin O Brien', 'Imperial College London',
  'We describe a microfluidic cell-free system capable of producing infectious recombinant viral particles from DNA templates in under 6 hours using only commercially available reagents and standard laboratory equipment.',
  'biorxiv', '2026-03-05', 'Bioengineering', 1, 'methods_analysed', 'medium', 6, 'monitor', 'false_positive',
  '{"summary": "Benchtop viral particle production platform. Dual-use concern for lowering barriers.", "dimensions": {"pathogen_enhancement": {"score": 0, "justification": "Platform paper, no pathogen work"}, "synthesis_barrier_lowering": {"score": 2, "justification": "Simplifies viral particle production"}, "select_agent_relevance": {"score": 0, "justification": "Demonstrated with non-pathogenic viruses"}, "novel_technique": {"score": 2, "justification": "Novel microfluidic approach"}, "information_hazard": {"score": 1, "justification": "Detailed protocol but uses commercial reagents"}, "defensive_framing": {"score": 1, "justification": "Discusses misuse briefly"}}, "aggregate_score": 6}'::jsonb,
  now() - interval '12 days', now() - interval '12 days'
);

-- Paper 8: Low - Monkeypox structural biology
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.03.03.008',
  'Structural basis for monkeypox virus immune evasion of human complement system',
  '[{"name": "Rachel Kim"}, {"name": "Paul Nguyen"}]'::jsonb,
  'Rachel Kim', 'NIH/NIAID Rocky Mountain Laboratories',
  'We determine the crystal structure of monkeypox virus complement control protein at 1.8A resolution, revealing the molecular mechanism by which the virus evades human innate immunity.',
  'biorxiv', '2026-03-03', 'Structural Biology', 1, 'methods_analysed', 'low', 4, 'archive', 'archived',
  '{"summary": "Structural biology of poxvirus immune evasion. Low concern - defensive research.", "dimensions": {"pathogen_enhancement": {"score": 1, "justification": "Characterises evasion but identifies ablating mutations"}, "synthesis_barrier_lowering": {"score": 0, "justification": "No synthesis work"}, "select_agent_relevance": {"score": 1, "justification": "Monkeypox is a select agent but work is defensive"}, "novel_technique": {"score": 0, "justification": "Standard structural biology"}, "information_hazard": {"score": 1, "justification": "Structural details of immune evasion"}, "defensive_framing": {"score": 1, "justification": "Clearly framed as therapeutic target identification"}}, "aggregate_score": 4}'::jsonb,
  now() - interval '14 days', now() - interval '14 days'
);

-- Paper 9: Low - Coronavirus vaccine
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.02.28.009',
  'mRNA vaccine platform targeting conserved epitopes across betacoronavirus lineages',
  '[{"name": "Emily Watson"}, {"name": "Carlos Rivera"}, {"name": "Fatima Al-Rashid"}]'::jsonb,
  'Emily Watson', 'University of Oxford',
  'We present a pan-betacoronavirus mRNA vaccine candidate targeting conserved T-cell epitopes in the replicase polyprotein. In non-human primates, the vaccine elicited cross-reactive T-cell responses against SARS-CoV-2, SARS-CoV-1, and MERS-CoV.',
  'medrxiv', '2026-02-28', 'Immunology', 1, 'methods_analysed', 'low', 2, 'archive', 'archived',
  '{"summary": "Pan-coronavirus vaccine. Clearly defensive research with no dual-use concerns.", "dimensions": {"pathogen_enhancement": {"score": 0, "justification": "Vaccine development"}, "synthesis_barrier_lowering": {"score": 0, "justification": "Standard mRNA platform"}, "select_agent_relevance": {"score": 1, "justification": "Works with coronavirus antigens"}, "novel_technique": {"score": 1, "justification": "Novel epitope selection"}, "information_hazard": {"score": 0, "justification": "Not weaponizable"}, "defensive_framing": {"score": 0, "justification": "Entirely defensive"}}, "aggregate_score": 2}'::jsonb,
  now() - interval '18 days', now() - interval '18 days'
);

-- Paper 10: Low - Surveillance study
INSERT INTO papers (id, doi, title, authors, corresponding_author, corresponding_institution, abstract, source_server, posted_date, subject_category, version, pipeline_stage, risk_tier, aggregate_score, recommended_action, review_status, stage2_result, created_at, updated_at)
VALUES (
  gen_random_uuid(), '10.1101/2026.02.25.010',
  'Genomic surveillance of avian influenza H7N9 reassortment events in live poultry markets',
  '[{"name": "Hui Zhang"}, {"name": "Michael Brown"}, {"name": "Akiko Iwasaki"}]'::jsonb,
  'Hui Zhang', 'Chinese Center for Disease Control and Prevention',
  'We performed longitudinal genomic surveillance of H7N9 avian influenza in 47 live poultry markets across southern China over 24 months, identifying 12 novel reassortant genotypes.',
  'pubmed', '2026-02-25', 'Epidemiology', 1, 'methods_analysed', 'low', 3, 'archive', 'unreviewed',
  '{"summary": "Surveillance study of avian flu reassortment. Low concern - public health monitoring.", "dimensions": {"pathogen_enhancement": {"score": 0, "justification": "Surveillance only"}, "synthesis_barrier_lowering": {"score": 0, "justification": "No synthesis"}, "select_agent_relevance": {"score": 1, "justification": "H7N9 is a select agent but observational"}, "novel_technique": {"score": 0, "justification": "Standard genomic surveillance"}, "information_hazard": {"score": 1, "justification": "Identifies reassortant genotypes"}, "defensive_framing": {"score": 1, "justification": "Public health framing"}}, "aggregate_score": 3}'::jsonb,
  now() - interval '20 days', now() - interval '20 days'
);

-- Pipeline runs
INSERT INTO pipeline_runs (id, started_at, finished_at, papers_ingested, papers_after_dedup, papers_coarse_passed, papers_fulltext_retrieved, papers_methods_analysed, papers_enriched, papers_adjudicated, errors, total_cost_usd, trigger)
VALUES (gen_random_uuid(), now() - interval '1 hour', now() - interval '30 minutes', 4832, 4210, 187, 142, 138, 95, 12, null, 8.42, 'scheduled');

INSERT INTO pipeline_runs (id, started_at, finished_at, papers_ingested, papers_after_dedup, papers_coarse_passed, papers_fulltext_retrieved, papers_methods_analysed, papers_enriched, papers_adjudicated, errors, total_cost_usd, trigger)
VALUES (gen_random_uuid(), now() - interval '25 hours', now() - interval '24 hours', 5104, 4456, 203, 156, 151, 102, 15, '["Failed to retrieve full text for 10.1101/2026.03.14.999"]'::jsonb, 9.15, 'scheduled');

INSERT INTO pipeline_runs (id, started_at, finished_at, papers_ingested, papers_after_dedup, papers_coarse_passed, papers_fulltext_retrieved, papers_methods_analysed, papers_enriched, papers_adjudicated, errors, total_cost_usd, trigger)
VALUES (gen_random_uuid(), now() - interval '49 hours', now() - interval '48 hours', 4920, 4302, 195, 148, 144, 98, 13, null, 8.78, 'scheduled');
