CREATE SCHEMA stackexchange_db
       AUTHORIZATION stackexchange_bot;

create table stackexchange_db.sites
(
    id serial primary key,
    api_site_parameter varchar(1024) not null,
    dt_created  timestamp with time zone default current_timestamp
);
create unique index u_sites_api_site_parameter on stackexchange_db.sites(api_site_parameter);
alter table stackexchange_db.sites owner to stackexchange_bot;

create table stackexchange_db.update_statuses
(
    id integer primary key,
    v_name varchar(255)
);
alter table stackexchange_db.update_statuses owner to stackexchange_bot;
insert into stackexchange_db.update_statuses (id, v_name) values (1, 'Done');
insert into stackexchange_db.update_statuses (id, v_name) values (2, 'Processing');

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

create table stackexchange_db.subscriptions
(
    id serial primary key,
    telegram_id bigint not null,
    site_id integer not null,
    tags jsonb,
    dt_created  timestamp with time zone default current_timestamp
);
alter table stackexchange_db.subscriptions ADD CONSTRAINT fk_subscriptions_to_sites foreign key (site_id) references  stackexchange_db.sites(id);
alter table stackexchange_db.subscriptions owner to stackexchange_bot;

create table stackexchange_db.version
(
	v_name varchar(255),
	n_version integer,
	dt_update timestamp with time zone
);
alter table  stackexchange_db.version owner to achievements_hunt_bot;
insert into stackexchange_db.version(v_name, n_version, dt_update) values('Stackexchange bot', 1, current_timestamp);
commit;