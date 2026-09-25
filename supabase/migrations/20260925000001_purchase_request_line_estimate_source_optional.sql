-- R4.3 Phase 5 (T027): purchase_request_line's estimated price can now come from a source
-- other than the landed-cost pipeline -- specifically, an RFQ response's raw quoted price
-- (plan.md's own Task 4: "the winning response's quoted price, not landed cost"). The original
-- constraint required estimated_unit_price_source_landed_cost_id to be set whenever a price is
-- set, which only ever held while landed cost was the ONLY estimation source. It no longer
-- should: estimated_unit_price_source_landed_cost_id is now an optional provenance pointer, not
-- a requirement for having a price at all. amount/currency pairing with EACH OTHER is unchanged.
alter table purchase_request_line drop constraint purchase_request_line_estimate_paired;
alter table purchase_request_line add constraint purchase_request_line_estimate_paired
  check ((estimated_unit_price_amount is null) = (estimated_unit_price_currency is null));
