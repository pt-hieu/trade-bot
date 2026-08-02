-- Fix catalyst_type for Hormuz crisis (defaulted to 'regulatory')
UPDATE catalysts
SET catalyst_type = 'geopolitical',
    discovery_source = 'manual_151'
WHERE catalyst_key = 'hormuz_closure_2026';
