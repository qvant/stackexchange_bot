create table stackexchange_db.site_updates
(
    id serial primary key,
    site_id integer not null,
    last_question_id bigint,
    last_question_time bigint,
    dt_next_update timestamp with time zone not null,
    update_status_id integer
);
create unique index u_site_updates_site_id on stackexchange_db.site_updates(site_id);
alter table stackexchange_db.site_updates ADD CONSTRAINT fk_site_updates_to_statuses foreign key (update_status_id) references  stackexchange_db.update_statuses(id);
alter table stackexchange_db.site_updates ADD CONSTRAINT fk_site_updates_to_sites foreign key (site_id) references  stackexchange_db.sites(id);
alter table stackexchange_db.site_updates owner to stackexchange_bot;