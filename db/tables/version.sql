create table stackexchange_db.version
(
	v_name varchar(255),
	n_version integer,
	dt_update timestamp with time zone
);
alter table  stackexchange_db.version owner to achievements_hunt_bot;
insert into stackexchange_db.version(v_name, n_version, dt_update) values('Stackexchange bot', 1, current_timestamp);
commit;